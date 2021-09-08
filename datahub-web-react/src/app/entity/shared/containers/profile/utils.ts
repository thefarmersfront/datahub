import { useLocation } from 'react-router';
import queryString from 'query-string';
import { EntityType } from '../../../../../types.generated';
import useIsLineageMode from '../../../../lineage/utils/useIsLineageMode';
import { useEntityRegistry } from '../../../../useEntityRegistry';
import EntityRegistry from '../../../EntityRegistry';
import { EntityTab, GenericEntityProperties } from '../../types';

export function getDataForEntityType<T>({
    data,
    entityType,
    getOverrideProperties,
}: {
    data: T;
    entityType: EntityType;
    getOverrideProperties: (T) => GenericEntityProperties;
}): GenericEntityProperties | null {
    if (!data) {
        return null;
    }
    return {
        ...data[entityType.toLowerCase()],
        ...getOverrideProperties(data),
    };
}

export function getEntityPath(
    entityType: EntityType,
    urn: string,
    entityRegistry: EntityRegistry,
    isLineageMode: boolean,
    tabName?: string,
    tabParams?: Record<string, any>,
) {
    const tabParamsString = tabParams ? `&${queryString.stringify(tabParams)}` : '';

    if (!tabName) {
        return `/${entityRegistry.getPathName(entityType)}/${urn}?is_lineage_mode=${isLineageMode}${tabParamsString}`;
    }
    return `/${entityRegistry.getPathName(
        entityType,
    )}/${urn}/${tabName}?is_lineage_mode=${isLineageMode}${tabParamsString}`;
}

export function useEntityPath(entityType: EntityType, urn: string, tabName?: string, tabParams?: Record<string, any>) {
    const isLineageMode = useIsLineageMode();
    const entityRegistry = useEntityRegistry();
    return getEntityPath(entityType, urn, entityRegistry, isLineageMode, tabName, tabParams);
}

export function useRoutedTab(tabs: EntityTab[]): EntityTab | undefined {
    const { pathname } = useLocation();
    const trimmedPathName = pathname.endsWith('/') ? pathname.slice(0, pathname.length - 1) : pathname;
    const splitPathName = trimmedPathName.split('/');
    const lastTokenInPath = splitPathName[splitPathName.length - 1];
    const routedTab = tabs.find((tab) => tab.name === lastTokenInPath);
    return routedTab;
}

export function formatDateString(time: number) {
    const date = new Date(time);
    return date.toLocaleDateString('en-US');
}
