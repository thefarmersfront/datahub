package com.linkedin.metadata.search.elasticsearch.query;

import com.codahale.metrics.Timer;
import com.linkedin.metadata.dao.exception.ESQueryException;
import com.linkedin.metadata.models.EntitySpec;
import com.linkedin.metadata.models.registry.EntityRegistry;
import com.linkedin.metadata.query.AutoCompleteResult;
import com.linkedin.metadata.query.filter.Filter;
import com.linkedin.metadata.query.filter.SortCriterion;
import com.linkedin.metadata.search.SearchResult;
import com.linkedin.metadata.search.elasticsearch.query.request.AutocompleteRequestHandler;
import com.linkedin.metadata.search.elasticsearch.query.request.SearchRequestHandler;
import com.linkedin.metadata.utils.elasticsearch.IndexConvention;
import com.linkedin.metadata.utils.metrics.MetricUtils;
import io.opentelemetry.extension.annotations.WithSpan;
import java.io.IOException;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.elasticsearch.action.search.SearchRequest;
import org.elasticsearch.action.search.SearchResponse;
import org.elasticsearch.client.RequestOptions;
import org.elasticsearch.client.RestHighLevelClient;
import org.elasticsearch.client.core.CountRequest;
import org.elasticsearch.index.query.QueryBuilders;


/**
 * A search DAO for Elasticsearch backend.
 */
@Slf4j
@RequiredArgsConstructor
public class ESSearchDAO {

  private final EntityRegistry entityRegistry;
  private final RestHighLevelClient client;
  private final IndexConvention indexConvention;

  public long docCount(@Nonnull String entityName) {
    EntitySpec entitySpec = entityRegistry.getEntitySpec(entityName);
    CountRequest countRequest =
        new CountRequest(indexConvention.getIndexName(entitySpec)).query(QueryBuilders.matchAllQuery());
    try (Timer.Context ignored = MetricUtils.timer(this.getClass(), "docCount").time()) {
      return client.count(countRequest, RequestOptions.DEFAULT).getCount();
    } catch (IOException e) {
      log.error("Count query failed:" + e.getMessage());
      throw new ESQueryException("Count query failed:", e);
    }
  }

  @Nonnull
  @WithSpan
  private SearchResult executeAndExtract(@Nonnull EntitySpec entitySpec, @Nonnull SearchRequest searchRequest, int from,
      int size) {
    try (Timer.Context ignored = MetricUtils.timer(this.getClass(), "esSearch").time()) {
      final SearchResponse searchResponse = client.search(searchRequest, RequestOptions.DEFAULT);
      // extract results, validated against document model as well
      return SearchRequestHandler.getBuilder(entitySpec).extractResult(searchResponse, from, size);
    } catch (Exception e) {
      log.error("Search query failed:" + e.getMessage());
      throw new ESQueryException("Search query failed:", e);
    }
  }

  /**
   * Gets a list of documents that match given search request. The results are aggregated and filters are applied to the
   * search hits and not the aggregation results.
   *
   * @param input the search input text
   * @param postFilters the request map with fields and values as filters to be applied to search hits
   * @param sortCriterion {@link SortCriterion} to be applied to search results
   * @param from index to start the search from
   * @param size the number of search hits to return
   * @return a {@link com.linkedin.metadata.dao.SearchResult} that contains a list of matched documents and related search result metadata
   */
  @Nonnull
  public SearchResult search(@Nonnull String entityName, @Nonnull String input, @Nullable Filter postFilters,
      @Nullable SortCriterion sortCriterion, int from, int size) {
    Timer.Context searchRequestTimer = MetricUtils.timer(this.getClass(), "searchRequest").time();
    EntitySpec entitySpec = entityRegistry.getEntitySpec(entityName);
    // Step 1: construct the query
    final SearchRequest searchRequest =
        SearchRequestHandler.getBuilder(entitySpec).getSearchRequest(input, postFilters, sortCriterion, from, size);
    searchRequest.indices(indexConvention.getIndexName(entitySpec));
    searchRequestTimer.stop();
    // Step 2: execute the query and extract results, validated against document model as well
    return executeAndExtract(entitySpec, searchRequest, from, size);
  }

  /**
   * Gets a list of documents after applying the input filters.
   *
   * @param filters the request map with fields and values to be applied as filters to the search query
   * @param sortCriterion {@link SortCriterion} to be applied to search results
   * @param from index to start the search from
   * @param size number of search hits to return
   * @return a {@link com.linkedin.metadata.dao.SearchResult} that contains a list of filtered documents and related search result metadata
   */
  @Nonnull
  public SearchResult filter(@Nonnull String entityName, @Nullable Filter filters,
      @Nullable SortCriterion sortCriterion, int from, int size) {
    EntitySpec entitySpec = entityRegistry.getEntitySpec(entityName);
    final SearchRequest searchRequest =
        SearchRequestHandler.getBuilder(entitySpec).getFilterRequest(filters, sortCriterion, from, size);
    searchRequest.indices(indexConvention.getIndexName(entitySpec));
    return executeAndExtract(entitySpec, searchRequest, from, size);
  }

  /**
   * Returns a list of suggestions given type ahead query.
   *
   * <p>The advanced auto complete can take filters and provides suggestions based on filtered context.
   *
   * @param query the type ahead query text
   * @param field the field name for the auto complete
   * @param requestParams specify the field to auto complete and the input text
   * @param limit the number of suggestions returned
   * @return A list of suggestions as string
   */
  @Nonnull
  public AutoCompleteResult autoComplete(@Nonnull String entityName, @Nonnull String query, @Nullable String field,
      @Nullable Filter requestParams, int limit) {
    try {
      EntitySpec entitySpec = entityRegistry.getEntitySpec(entityName);
      AutocompleteRequestHandler builder = AutocompleteRequestHandler.getBuilder(entitySpec);
      SearchRequest req = builder.getSearchRequest(query, field, requestParams, limit);
      req.indices(indexConvention.getIndexName(entitySpec));
      SearchResponse searchResponse = client.search(req, RequestOptions.DEFAULT);
      return builder.extractResult(searchResponse, query);
    } catch (Exception e) {
      log.error("Auto complete query failed:" + e.getMessage());
      throw new ESQueryException("Auto complete query failed:", e);
    }
  }

  /**
   * Returns number of documents per field value given the field and filters
   *
   * @param entityName name of the entity
   * @param field the field name for aggregate
   * @param requestParams filters to apply before aggregating
   * @param limit the number of aggregations to return
   * @return
   */
  @Nonnull
  public Map<String, Long> aggregateByValue(@Nonnull String entityName, @Nonnull String field,
      @Nullable Filter requestParams, int limit) {
    EntitySpec entitySpec = entityRegistry.getEntitySpec(entityName);
    final SearchRequest searchRequest =
        SearchRequestHandler.getBuilder(entitySpec).getAggregationRequest(field, requestParams, limit);
    searchRequest.indices(indexConvention.getIndexName(entitySpec));
    return executeAndExtract(entitySpec, searchRequest, 0, 0).getMetadata()
        .getAggregations()
        .stream()
        .findFirst().<Map<String, Long>>map(aggregationMetadata -> new HashMap<>(aggregationMetadata.getAggregations()))
        .orElse(Collections.emptyMap());
  }
}
