"""P1 单元测试: SkillEmbeddingIndex + Hybrid RRF in SkillMatcher

注意：
- 这些测试需要 fastembed + onnxruntime；CI 跳过时用 pytest -k "not embedding"
- 测试模型可能在线下载，首次运行慢；后续使用 HF 缓存
"""
from __future__ import annotations

import os
import textwrap

import pytest


def _has_fastembed() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _has_fastembed(), reason="fastembed not installed")


# ============ Fixtures ============

VALID_SKILL_MD_TEMPLATE = textwrap.dedent("""\
    ---
    name: {name}
    description: {desc}
    domain: penetration-testing
    subdomain: exploitation
    tags: {tags}
    version: '2.0'
    ---
    ## Principle

    {principle}

    ## Detection Fingerprint

    {fingerprint}

    ## Workflow

    {workflow}

    ## Failure Modes

    | 现象 | 原因 |
    |------|------|
    | x | y |

    ## Generalization

    {generalization}
""")


@pytest.fixture
def skills_with_text(tmp_path):
    """构造一组覆盖不同主题的 skill，用于测试语义匹配能力"""
    skills_root = tmp_path / "skills"
    cat_dir = skills_root / "exploit-skills"
    cat_dir.mkdir(parents=True)
    spec = [
        ("exploit-apache-http", "Apache HTTP Server 2.4 路径遍历漏洞利用",
         "[apache, http, traversal]",
         "Apache 2.4.49/50 mod_alias 路径检查缺陷",
         "返回 banner Apache/2.4.49",
         "curl http://target/cgi-bin/.%2e/.%2e/etc/passwd",
         "适用所有 Apache 2.4.49-2.4.50 版本"),
        ("exploit-mysql-weak-creds", "MySQL 弱口令爆破",
         "[mysql, brute-force]",
         "MySQL 默认账号 root/root 等弱口令",
         "3306 端口开放，banner 含 MySQL",
         "hydra -L users -P pass mysql://target",
         "适用所有版本 MySQL 弱密码"),
        ("exploit-tomcat-default-creds", "Tomcat Manager 默认凭据 + WAR 上传",
         "[tomcat, java]",
         "Tomcat /manager/html 默认 tomcat/tomcat",
         "8080 端口返回 Apache Tomcat",
         "curl -u tomcat:tomcat -X POST http://target:8080/manager/text/deploy",
         "适用 Tomcat 6/7/8 默认配置"),
    ]
    for name, desc, tags, principle, fingerprint, workflow, generalization in spec:
        d = cat_dir / name
        d.mkdir()
        (d / "SKILL.md").write_text(VALID_SKILL_MD_TEMPLATE.format(
            name=name, desc=desc, tags=tags,
            principle=principle, fingerprint=fingerprint,
            workflow=workflow, generalization=generalization,
        ), encoding="utf-8")
    return str(skills_root)


# ============ Tests ============

def test_encoder_singleton_returns_same_instance():
    from app.services.skill_engine.encoder import get_encoder
    e1 = get_encoder()
    e2 = get_encoder()
    assert e1 is e2


def test_embedding_index_builds_and_searches(skills_with_text):
    from app.services.skill_engine import SkillLoader, SkillEmbeddingIndex
    loader = SkillLoader(skills_with_text)
    skills = loader.load_all()
    assert len(skills) >= 3

    cache_dir = os.path.join(skills_with_text, ".cache", "embeddings")
    index = SkillEmbeddingIndex(skills, cache_dir=cache_dir)
    assert index.build()
    assert index.available

    # Apache 路径遍历应能通过语义而非关键词命中
    results = index.search("httpd directory traversal vulnerability", top_k=3)
    assert len(results) > 0
    top_names = [r.skill.name for r in results]
    assert "exploit-apache-http" in top_names

    # 缓存文件应存在
    assert os.path.isfile(os.path.join(cache_dir, "skills.npy"))
    assert os.path.isfile(os.path.join(cache_dir, "skills_meta.json"))


def test_embedding_index_uses_cache_on_second_build(skills_with_text):
    """第二次构建应复用缓存（不重新编码）"""
    from app.services.skill_engine import SkillLoader, SkillEmbeddingIndex
    loader = SkillLoader(skills_with_text)
    skills = loader.load_all()

    cache_dir = os.path.join(skills_with_text, ".cache", "embeddings")
    index1 = SkillEmbeddingIndex(skills, cache_dir=cache_dir)
    assert index1.build()

    # 第二次：构造新 index，应命中缓存
    import time
    t0 = time.time()
    index2 = SkillEmbeddingIndex(skills, cache_dir=cache_dir)
    assert index2.build()
    elapsed = time.time() - t0
    # 缓存命中应该非常快（<2s 在 CPU 上）
    assert elapsed < 5.0, f"second build too slow: {elapsed:.2f}s, cache not hit"


def test_hybrid_matcher_finds_semantic_match(skills_with_text):
    """SkillMatcher 应能用 embedding 命中 keyword 不匹配的语义查询"""
    from app.services.skill_engine import SkillLoader, SkillMatcher
    loader = SkillLoader(skills_with_text)
    matcher = SkillMatcher(loader)

    # 查询用的术语与 skill 的 keyword 不完全一致：
    # "httpd" 不在 skill name/tags 里（只有 "apache"），但语义近
    matches = matcher.match("httpd directory traversal CVE", limit=3)
    assert len(matches) > 0
    names = [m.skill.name for m in matches]
    assert "exploit-apache-http" in names


def test_hybrid_matcher_respects_service_skill_map(skills_with_text):
    """SERVICE_SKILL_MAP 命中应保持高排序"""
    from app.services.skill_engine import SkillLoader, SkillMatcher
    loader = SkillLoader(skills_with_text)
    matcher = SkillMatcher(loader)

    # 含 "tomcat" 关键词，应让 exploit-tomcat-default-creds 高分
    matches = matcher.match("tomcat 8.5 deployment", limit=3)
    assert len(matches) > 0
    names = [m.skill.name for m in matches]
    assert "exploit-tomcat-default-creds" in names[:2]


def test_hybrid_matcher_falls_back_when_embedding_disabled(skills_with_text, monkeypatch):
    """禁用 embedding 时应回退到规则 + TF-IDF"""
    from app.services.skill_engine import SkillLoader, SkillMatcher
    loader = SkillLoader(skills_with_text)
    matcher = SkillMatcher(loader)
    matcher._embedding_index = False  # 模拟 embedding 加载失败
    matches = matcher.match("mysql brute force", limit=3)
    assert len(matches) > 0
    names = [m.skill.name for m in matches]
    assert "exploit-mysql-weak-creds" in names
