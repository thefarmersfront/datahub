import React from 'react';
import { useHistory } from 'react-router';
import { useTheme } from 'styled-components';

import { SearchHeader } from './SearchHeader';
import { useEntityRegistry } from '../useEntityRegistry';
import { EntityType } from '../../types.generated';
import { useGetAutoCompleteAllResultsLazyQuery } from '../../graphql/search.generated';
import { navigateToSearchUrl } from './utils/navigateToSearchUrl';
import { useGetAuthenticatedUser } from '../useGetAuthenticatedUser';
import analytics, { EventType } from '../analytics';

const styles = {
    children: {
        flex: '1',
        marginTop: 60,
        display: 'flex',
        flexDirection: 'column' as const,
    },
};

interface Props extends React.PropsWithChildren<any> {
    initialQuery?: string;
    onSearch?: (query: string, type?: EntityType) => void;
    onAutoComplete?: (query: string) => void;
}

const defaultProps = {
    initialQuery: '',
    onSearch: undefined,
    onAutoComplete: undefined,
};

/**
 * A page that includes a sticky search header (nav bar)
 */
export const SearchablePage = ({ initialQuery, onSearch, onAutoComplete, children }: Props) => {
    const history = useHistory();
    const entityRegistry = useEntityRegistry();
    const themeConfig = useTheme();

    const user = useGetAuthenticatedUser()?.corpUser;
    const [getAutoCompleteResults, { data: suggestionsData }] = useGetAutoCompleteAllResultsLazyQuery();

    const search = (query: string, type?: EntityType) => {
        if (!query || query.trim().length === 0) {
            return;
        }
        analytics.event({
            type: EventType.SearchEvent,
            query,
            pageNumber: 1,
            originPath: window.location.pathname,
        });

        navigateToSearchUrl({
            type,
            query,
            history,
            entityRegistry,
        });
    };

    const autoComplete = (query: string) => {
        getAutoCompleteResults({
            variables: {
                input: {
                    query,
                },
            },
        });
    };

    return (
        <>
            <SearchHeader
                initialQuery={initialQuery as string}
                placeholderText={themeConfig.content.search.searchbarMessage}
                suggestions={
                    (suggestionsData &&
                        suggestionsData?.autoCompleteForAll &&
                        suggestionsData.autoCompleteForAll.suggestions) ||
                    []
                }
                onSearch={onSearch || search}
                onQueryChange={onAutoComplete || autoComplete}
                authenticatedUserUrn={user?.urn || ''}
                authenticatedUserPictureLink={user?.editableInfo?.pictureLink}
                entityRegistry={entityRegistry}
            />
            <div style={styles.children}>{children}</div>
        </>
    );
};

SearchablePage.defaultProps = defaultProps;
