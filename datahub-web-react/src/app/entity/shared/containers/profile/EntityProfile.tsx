import React, { useCallback } from 'react';
import { Alert, Divider } from 'antd';
import { MutationHookOptions, MutationTuple, QueryHookOptions, QueryResult } from '@apollo/client/react/types/types';
import styled from 'styled-components';
import { useHistory } from 'react-router';

import { EntityType, Exact } from '../../../../../types.generated';
import { Message } from '../../../../shared/Message';
import { getDataForEntityType, getEntityPath, useRoutedTab } from './utils';
import { EntitySidebarSection, EntityTab, GenericEntityProperties, GenericEntityUpdate } from '../../types';
import { EntityProfileNavBar } from './nav/EntityProfileNavBar';
import { ANTD_GRAY } from '../../constants';
import { EntityHeader } from './header/EntityHeader';
import { EntityTabs } from './header/EntityTabs';
import { EntitySidebar } from './sidebar/EntitySidebar';
import EntityContext from '../../EntityContext';
import useIsLineageMode from '../../../../lineage/utils/useIsLineageMode';
import { useEntityRegistry } from '../../../../useEntityRegistry';
import LineageExplorer from '../../../../lineage/LineageExplorer';
import CompactContext from '../../../../shared/CompactContext';

type Props<T, U> = {
    urn: string;
    entityType: EntityType;
    useEntityQuery: (
        baseOptions: QueryHookOptions<
            T,
            Exact<{
                urn: string;
            }>
        >,
    ) => QueryResult<
        T,
        Exact<{
            urn: string;
        }>
    >;
    useUpdateQuery: (
        baseOptions?: MutationHookOptions<U, { input: GenericEntityUpdate }> | undefined,
    ) => MutationTuple<U, { input: GenericEntityUpdate }>;
    getOverrideProperties: (T) => GenericEntityProperties;
    tabs: EntityTab[];
    sidebarSections: EntitySidebarSection[];
};

const ContentContainer = styled.div`
    display: flex;
    height: auto;
    min-height: 100%;
    max-height: calc(100vh - 108px);
    align-items: stretch;
    flex: 1;
`;

const HeaderAndTabs = styled.div`
    flex-basis: 70%;
    min-width: 640px;
`;
const HeaderAndTabsFlex = styled.div`
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100%;
    max-height: 100%;
    overflow: hidden;
    min-height: 0;
`;
const Sidebar = styled.div`
    overflow: auto;
    flex-basis: 30%;
    border-left: 1px solid ${ANTD_GRAY[4.5]};
    padding-left: 20px;
    padding-right: 20px;
`;

const Header = styled.div`
    border-bottom: 1px solid ${ANTD_GRAY[4.5]};
    padding: 20px 20px 0 20px;
    flex-shrink: 0;
    height: 137px;
`;

const TabContent = styled.div`
    flex: 1;
    overflow: auto;
`;

// TODO(Gabe): Refactor this to generate dynamically
const QUERY_NAME = 'getDataset';

/**
 * Container for display of the Entity Page
 */
export const EntityProfile = <T, U>({
    urn,
    useEntityQuery,
    useUpdateQuery,
    entityType,
    getOverrideProperties,
    tabs,
    sidebarSections,
}: Props<T, U>): JSX.Element => {
    const routedTab = useRoutedTab(tabs);
    const isLineageMode = useIsLineageMode();
    const entityRegistry = useEntityRegistry();
    const history = useHistory();
    const isCompact = React.useContext(CompactContext);

    const routeToTab = useCallback(
        ({
            tabName,
            tabParams,
            method = 'push',
        }: {
            tabName: string;
            tabParams?: Record<string, any>;
            method?: 'push' | 'replace';
        }) => {
            history[method](getEntityPath(entityType, urn, entityRegistry, false, tabName, tabParams));
        },
        [history, entityType, urn, entityRegistry],
    );

    const { loading, error, data, refetch } = useEntityQuery({ variables: { urn } });

    const [updateEntity] = useUpdateQuery({
        refetchQueries: () => [QUERY_NAME],
    });

    const entityData = getDataForEntityType({ data, entityType, getOverrideProperties });

    if (isCompact) {
        return (
            <EntityContext.Provider
                value={{
                    urn,
                    entityType,
                    entityData,
                    baseEntity: data,
                    updateEntity,
                    routeToTab,
                    refetch,
                }}
            >
                <div>
                    {loading && <Message type="loading" content="Loading..." style={{ marginTop: '10%' }} />}
                    {!loading && error && (
                        <Alert type="error" message={error?.message || `Entity failed to load for urn ${urn}`} />
                    )}
                    {!loading && (
                        <>
                            <EntityHeader />
                            <Divider />
                            <EntitySidebar sidebarSections={sidebarSections} />
                        </>
                    )}
                </div>
            </EntityContext.Provider>
        );
    }

    return (
        <EntityContext.Provider
            value={{
                urn,
                entityType,
                entityData,
                baseEntity: data,
                updateEntity,
                routeToTab,
                refetch,
            }}
        >
            <>
                <EntityProfileNavBar urn={urn} entityData={entityData} entityType={entityType} />
                {loading && <Message type="loading" content="Loading..." style={{ marginTop: '10%' }} />}
                {!loading && error && (
                    <Alert type="error" message={error?.message || `Entity failed to load for urn ${urn}`} />
                )}
                <ContentContainer>
                    {isLineageMode ? (
                        <LineageExplorer type={entityType} urn={urn} />
                    ) : (
                        <>
                            <HeaderAndTabs>
                                <HeaderAndTabsFlex>
                                    <Header>
                                        <EntityHeader />
                                        <EntityTabs tabs={tabs} selectedTab={routedTab} />
                                    </Header>
                                    <TabContent>{routedTab && <routedTab.component />}</TabContent>
                                </HeaderAndTabsFlex>
                            </HeaderAndTabs>
                            <Sidebar>
                                <EntitySidebar sidebarSections={sidebarSections} />
                            </Sidebar>
                        </>
                    )}
                </ContentContainer>
            </>
        </EntityContext.Provider>
    );
};
