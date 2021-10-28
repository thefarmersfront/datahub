package com.linkedin.datahub.graphql.resolvers.search;

import com.linkedin.datahub.graphql.exception.ValidationException;
import com.linkedin.datahub.graphql.generated.SearchInput;
import com.linkedin.datahub.graphql.generated.SearchResults;
import com.linkedin.datahub.graphql.resolvers.EntityTypeMapper;
import com.linkedin.datahub.graphql.resolvers.ResolverUtils;
import com.linkedin.datahub.graphql.types.mappers.UrnSearchResultsMapper;
import com.linkedin.entity.client.RestliEntityClient;
import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;
import java.util.concurrent.CompletableFuture;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

import static com.linkedin.datahub.graphql.resolvers.ResolverUtils.bindArgument;
import static org.apache.commons.lang3.StringUtils.isBlank;


/**
 * Resolver responsible for resolving the 'search' field of the Query type
 */
@Slf4j
@RequiredArgsConstructor
public class SearchResolver implements DataFetcher<CompletableFuture<SearchResults>> {

  private static final int DEFAULT_START = 0;
  private static final int DEFAULT_COUNT = 10;

  private final RestliEntityClient _entityClient;

  @Override
  public CompletableFuture<SearchResults> get(DataFetchingEnvironment environment) {
    final SearchInput input = bindArgument(environment.getArgument("input"), SearchInput.class);
    final String entityName = EntityTypeMapper.getName(input.getType());
    // escape forward slash since it is a reserved character in Elasticsearch
    final String sanitizedQuery = ResolverUtils.escapeForwardSlash(input.getQuery());
    if (isBlank(sanitizedQuery)) {
      log.error("'query' parameter cannot was null or empty");
      throw new ValidationException("'query' parameter cannot be null or empty");
    }

    final int start = input.getStart() != null ? input.getStart() : DEFAULT_START;
    final int count = input.getCount() != null ? input.getCount() : DEFAULT_COUNT;

    return CompletableFuture.supplyAsync(() -> {
      try {
        log.debug("Executing search. entity type {}, query {}, filters: {}, start: {}, count: {}", input.getType(),
            input.getQuery(), input.getFilters(), start, count);
        return UrnSearchResultsMapper.map(
            _entityClient.search(entityName, sanitizedQuery, ResolverUtils.buildFilter(input.getFilters()), start,
                count, ResolverUtils.getActor(environment)));
      } catch (Exception e) {
        log.error("Failed to execute search: entity type {}, query {}, filters: {}, start: {}, count: {}",
            input.getType(), input.getQuery(), input.getFilters(), start, count);
        throw new RuntimeException(
            "Failed to execute search: " + String.format("entity type %s, query %s, filters: %s, start: %s, count: %s",
                input.getType(), input.getQuery(), input.getFilters(), start, count), e);
      }
    });
  }
}
