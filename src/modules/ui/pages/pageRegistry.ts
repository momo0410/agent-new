import type { AppPage } from '../pageTypes';

export interface PageDefinition {
  id: AppPage;
  render: () => string;
}

export function getPageDefinitionMap(definitions: PageDefinition[]): Record<AppPage, PageDefinition> {
  return definitions.reduce((map, definition) => {
    map[definition.id] = definition;
    return map;
  }, {} as Record<AppPage, PageDefinition>);
}
