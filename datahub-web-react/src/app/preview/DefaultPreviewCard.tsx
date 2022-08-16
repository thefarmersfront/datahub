import React, { ReactNode } from 'react';
import { Button, Divider, Tooltip, Typography } from 'antd';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { ArrowRightOutlined } from '@ant-design/icons';

import {
    GlobalTags,
    Owner,
    GlossaryTerms,
    SearchInsight,
    Container,
    ParentContainersResult,
    Maybe,
    CorpUser,
    Deprecation,
    Domain,
} from '../../types.generated';
import TagTermGroup from '../shared/tags/TagTermGroup';
import { ANTD_GRAY } from '../entity/shared/constants';
import NoMarkdownViewer from '../entity/shared/components/styled/StripMarkdownText';
import { getNumberWithOrdinal } from '../entity/shared/utils';
import { useEntityData } from '../entity/shared/EntityContext';
import PlatformContentView from '../entity/shared/containers/profile/header/PlatformContent/PlatformContentView';
import { useParentContainersTruncation } from '../entity/shared/containers/profile/header/PlatformContent/PlatformContentContainer';
import EntityCount from '../entity/shared/containers/profile/header/EntityCount';
import { ExpandedActorGroup } from '../entity/shared/components/styled/ExpandedActorGroup';
import { DeprecationPill } from '../entity/shared/components/styled/DeprecationPill';

const PreviewContainer = styled.div`
    display: flex;
    width: 100%;
    justify-content: space-between;
    align-items: center;
`;

const LeftColumn = styled.div`
    max-width: 60%;
`;

const RightColumn = styled.div`
    max-width: 40%;
    display: flex;
`;

const TitleContainer = styled.div`
    margin-bottom: 5px;
    line-height: 30px;

    .entityCount {
        margin-bottom: 2px;
    }
`;

const EntityTitleContainer = styled.div`
    display: flex;
    align-items: center;
`;

const EntityTitle = styled(Typography.Text)<{ $titleSizePx?: number }>`
    display: block;
    &&&:hover {
        text-decoration: underline;
    }

    &&& {
        margin-right 8px;
        font-size: ${(props) => props.$titleSizePx || 16}px;
        font-weight: 600;
        vertical-align: middle;
    }
`;

const PlatformText = styled(Typography.Text)`
    font-size: 12px;
    line-height: 20px;
    font-weight: 700;
    color: ${ANTD_GRAY[7]};
`;

const PlatformDivider = styled.div`
    display: inline-block;
    padding-left: 10px;
    margin-right: 10px;
    border-right: 1px solid ${ANTD_GRAY[4]};
    height: 21px;
    vertical-align: text-top;
`;

const DescriptionContainer = styled.div`
    color: ${ANTD_GRAY[7]};
    margin-bottom: 8px;
`;

const TagContainer = styled.div`
    display: inline-flex;
    margin-left: 0px;
    margin-top: 3px;
    flex-wrap: wrap;
`;

const TagSeparator = styled.div`
    margin: 2px 8px 0 0;
    height: 17px;
    border-right: 1px solid #cccccc;
`;

const InsightContainer = styled.div`
    margin-top: 12px;
`;

const InsightsText = styled(Typography.Text)`
    font-size: 12px;
    line-height: 20px;
    font-weight: 600;
    color: ${ANTD_GRAY[7]};
`;

const InsightIconContainer = styled.span`
    margin-right: 4px;
`;

const ExternalUrlContainer = styled.span`
    font-size: 12px;
`;

const ExternalUrlButton = styled(Button)`
    > :hover {
        text-decoration: underline;
    }
    &&& {
        padding-bottom: 0px;
    }
    padding-left: 12px;
    padding-right: 12px;
`;

const UserListContainer = styled.div`
    display: flex;
    flex-direction: column;
    justify-content: right;
    margin-right: 8px;
`;

const UserListDivider = styled(Divider)`
    padding: 4px;
    height: auto;
`;

const UserListTitle = styled(Typography.Text)`
    text-align: right;
    margin-bottom: 10px;
    padding-right: 12px;
`;

interface Props {
    name: string;
    logoUrl?: string;
    logoComponent?: JSX.Element;
    url: string;
    description?: string;
    type?: string;
    typeIcon?: JSX.Element;
    platform?: string;
    platformInstanceId?: string;
    platforms?: Maybe<string | undefined>[];
    logoUrls?: Maybe<string | undefined>[];
    qualifier?: string | null;
    tags?: GlobalTags;
    owners?: Array<Owner> | null;
    deprecation?: Deprecation | null;
    topUsers?: Array<CorpUser> | null;
    externalUrl?: string | null;
    subHeader?: React.ReactNode;
    snippet?: React.ReactNode;
    insights?: Array<SearchInsight> | null;
    glossaryTerms?: GlossaryTerms;
    container?: Container;
    domain?: Domain | undefined | null;
    entityCount?: number;
    dataTestID?: string;
    titleSizePx?: number;
    onClick?: () => void;
    // this is provided by the impact analysis view. it is used to display
    // how the listed node is connected to the source node
    degree?: number;
    parentContainers?: ParentContainersResult | null;
}

export default function DefaultPreviewCard({
    name,
    logoUrl,
    logoComponent,
    url,
    description,
    type,
    typeIcon,
    platform,
    platformInstanceId,
    // TODO(Gabe): support qualifier in the new preview card
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    qualifier,
    tags,
    owners,
    topUsers,
    subHeader,
    snippet,
    insights,
    glossaryTerms,
    domain,
    container,
    deprecation,
    entityCount,
    titleSizePx,
    dataTestID,
    externalUrl,
    onClick,
    degree,
    parentContainers,
    platforms,
    logoUrls,
}: Props) {
    // sometimes these lists will be rendered inside an entity container (for example, in the case of impact analysis)
    // in those cases, we may want to enrich the preview w/ context about the container entity
    const { entityData } = useEntityData();
    const insightViews: Array<ReactNode> = [
        ...(insights?.map((insight) => (
            <>
                <InsightIconContainer>{insight.icon}</InsightIconContainer>
                <InsightsText>{insight.text}</InsightsText>
            </>
        )) || []),
    ];
    const hasGlossaryTerms = !!glossaryTerms?.terms?.length;
    const hasTags = !!tags?.tags?.length;
    if (snippet) {
        insightViews.push(snippet);
    }

    const { parentContainersRef, areContainersTruncated } = useParentContainersTruncation(container);

    const onPreventMouseDown = (event) => {
        event.preventDefault();
        event.stopPropagation();
    };

    return (
        <PreviewContainer data-testid={dataTestID} onMouseDown={onPreventMouseDown}>
            <LeftColumn>
                <TitleContainer>
                    <PlatformContentView
                        platformName={platform}
                        platformLogoUrl={logoUrl}
                        platformNames={platforms}
                        platformLogoUrls={logoUrls}
                        entityLogoComponent={logoComponent}
                        instanceId={platformInstanceId}
                        typeIcon={typeIcon}
                        entityType={type}
                        parentContainers={parentContainers?.containers}
                        parentContainersRef={parentContainersRef}
                        areContainersTruncated={areContainersTruncated}
                    />
                    <EntityTitleContainer>
                        <Link to={url}>
                            <EntityTitle onClick={onClick} $titleSizePx={titleSizePx}>
                                {name || ' '}
                            </EntityTitle>
                        </Link>
                        {deprecation?.deprecated && <DeprecationPill deprecation={deprecation} preview />}
                        {externalUrl && (
                            <ExternalUrlContainer>
                                <ExternalUrlButton type="link" href={externalUrl} target="_blank">
                                    View in {platform} <ArrowRightOutlined style={{ fontSize: 12 }} />
                                </ExternalUrlButton>
                            </ExternalUrlContainer>
                        )}
                    </EntityTitleContainer>

                    {degree !== undefined && degree !== null && (
                        <Tooltip
                            title={`This entity is a ${getNumberWithOrdinal(degree)} degree connection to ${
                                entityData?.name || 'the source entity'
                            }`}
                        >
                            <PlatformText>{getNumberWithOrdinal(degree)}</PlatformText>
                        </Tooltip>
                    )}
                    {!!degree && entityCount && <PlatformDivider />}
                    <EntityCount entityCount={entityCount} />
                </TitleContainer>
                {description && description.length > 0 && (
                    <DescriptionContainer>
                        <NoMarkdownViewer limit={250}>{description}</NoMarkdownViewer>
                    </DescriptionContainer>
                )}
                {(domain || hasGlossaryTerms || hasTags) && (
                    <TagContainer>
                        {domain && <TagTermGroup domain={domain} maxShow={3} />}
                        {domain && hasGlossaryTerms && <TagSeparator />}
                        {hasGlossaryTerms && <TagTermGroup uneditableGlossaryTerms={glossaryTerms} maxShow={3} />}
                        {((hasGlossaryTerms && hasTags) || (domain && hasTags)) && <TagSeparator />}
                        {hasTags && <TagTermGroup uneditableTags={tags} maxShow={3} />}
                    </TagContainer>
                )}
                {subHeader}
                {insightViews.length > 0 && (
                    <InsightContainer>
                        {insightViews.map((insightView, index) => (
                            <span>
                                {insightView}
                                {index < insightViews.length - 1 && <PlatformDivider />}
                            </span>
                        ))}
                    </InsightContainer>
                )}
            </LeftColumn>
            <RightColumn>
                {topUsers && topUsers?.length > 0 && (
                    <>
                        <UserListContainer>
                            <UserListTitle strong>Top Users</UserListTitle>
                            <div>
                                <ExpandedActorGroup actors={topUsers} max={2} />
                            </div>
                        </UserListContainer>
                    </>
                )}
                {(topUsers?.length || 0) > 0 && (owners?.length || 0) > 0 && <UserListDivider type="vertical" />}
                {owners && owners?.length > 0 && (
                    <UserListContainer>
                        <UserListTitle strong>Owners</UserListTitle>
                        <div>
                            <ExpandedActorGroup actors={owners.map((owner) => owner.owner)} max={2} />
                        </div>
                    </UserListContainer>
                )}
            </RightColumn>
        </PreviewContainer>
    );
}
