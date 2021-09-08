import React, { useContext } from 'react';
import { EntityType } from '../../../types.generated';
import { EntityContextType, UpdateEntityType } from './types';

const EntityContext = React.createContext<EntityContextType>({
    urn: '',
    entityType: EntityType.Dataset,
    entityData: null,
    baseEntity: null,
    updateEntity: () => Promise.resolve({}),
    routeToTab: () => {},
});

export default EntityContext;

export const useBaseEntity = <T,>(): T => {
    const { baseEntity } = useContext(EntityContext);
    return baseEntity as T;
};

export const useEntityUpdate = <U,>(): UpdateEntityType<U> => {
    const { updateEntity } = useContext(EntityContext);
    return updateEntity as UpdateEntityType<U>;
};

export const useEntityData = () => {
    const { urn, entityType, entityData } = useContext(EntityContext);
    return { urn, entityType, entityData };
};

export const useRouteToTab = () => {
    const { routeToTab } = useContext(EntityContext);
    return routeToTab;
};
