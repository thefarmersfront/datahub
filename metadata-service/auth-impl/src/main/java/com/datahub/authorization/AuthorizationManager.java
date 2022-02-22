package com.datahub.authorization;

import com.datahub.authentication.Authentication;
import com.google.common.annotations.VisibleForTesting;
import com.linkedin.common.Owner;
import com.linkedin.common.Ownership;
import com.linkedin.common.urn.Urn;
import com.linkedin.entity.EntityResponse;
import com.linkedin.entity.EnvelopedAspectMap;
import com.linkedin.entity.client.EntityClient;
import com.linkedin.entity.client.OwnershipClient;
import com.linkedin.metadata.authorization.PoliciesConfig;
import com.linkedin.metadata.query.ListUrnsResult;
import com.linkedin.policy.DataHubPolicyInfo;
import com.linkedin.r2.RemoteInvocationException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;

import static com.linkedin.metadata.Constants.*;


/**
 * The Authorizer is a singleton class responsible for authorizing
 * operations on the DataHub platform.
 *
 * Currently, the authorizer is implemented as a spring-instantiated Singleton
 * which manages its own thread-pool used for resolving policy predicates.
 */
// TODO: Decouple this from all Rest.li objects if possible.
@Slf4j
public class AuthorizationManager implements Authorizer {

  // Credentials used to make / authorize requests as the internal system actor.
  private final Authentication _systemAuthentication;

  // Maps privilege name to the associated set of policies for fast access.
  // Not concurrent data structure because writes are always against the entire thing.
  private final Map<String, List<DataHubPolicyInfo>> _policyCache = new HashMap<>(); // Shared Policy Cache.

  private final ScheduledExecutorService _refreshExecutorService = Executors.newScheduledThreadPool(1);
  private final PolicyRefreshRunnable _policyRefreshRunnable;

  private final PolicyEngine _policyEngine;
  private AuthorizationMode _mode;

  public AuthorizationManager(
      final Authentication systemAuthentication,
      final EntityClient entityClient,
      final OwnershipClient ownershipClient,
      final int delayIntervalSeconds,
      final int refreshIntervalSeconds,
      final AuthorizationMode mode) {
    _systemAuthentication = systemAuthentication;
    _policyRefreshRunnable = new PolicyRefreshRunnable(systemAuthentication, entityClient, _policyCache);
    _refreshExecutorService.scheduleAtFixedRate(_policyRefreshRunnable, delayIntervalSeconds, refreshIntervalSeconds, TimeUnit.SECONDS);
    _mode = mode;
    _policyEngine = new PolicyEngine(systemAuthentication, entityClient, ownershipClient);
  }

  public AuthorizationResult authorize(final AuthorizationRequest request) {

    // 0. Short circuit: If the action is being performed by the system (root), always allow it.
    if (isSystemRequest(request, this._systemAuthentication)) {
      return new AuthorizationResult(request, Optional.empty(), AuthorizationResult.Type.ALLOW);
    }

    // 1. Fetch the policies relevant to the requested privilege.
    final List<DataHubPolicyInfo> policiesToEvaluate = _policyCache.getOrDefault(request.privilege(), new ArrayList<>());

    // 2. Evaluate each policy.
    for (DataHubPolicyInfo policy : policiesToEvaluate) {
      if (isRequestGranted(policy, request)) {
        // Short circuit if policy has granted privileges to this actor.
        return new AuthorizationResult(request, Optional.of(policy), AuthorizationResult.Type.ALLOW);
      }
    }
    return new AuthorizationResult(request, Optional.empty(), AuthorizationResult.Type.DENY);
  }

  /**
   * Retrieves the current list of actors authorized to for a particular privilege against
   * an optional resource
   */
  public AuthorizedActors authorizedActors(final String privilege, final Optional<ResourceSpec> resourceSpec) throws RuntimeException {
    // Step 1: Find policies granting the privilege.
    final List<DataHubPolicyInfo> policiesToEvaluate = _policyCache.getOrDefault(privilege, new ArrayList<>());

    final List<Urn> authorizedUsers = new ArrayList<>();
    final List<Urn> authorizedGroups = new ArrayList<>();
    boolean allUsers = false;
    boolean allGroups = false;

    // Step 2: For each policy, determine whether the resource is a match.
    for (DataHubPolicyInfo policy : policiesToEvaluate) {
      if (!PoliciesConfig.ACTIVE_POLICY_STATE.equals(policy.getState())) {
        // Policy is not active, skip.
        continue;
      }

      final PolicyEngine.PolicyActors matchingActors = _policyEngine.getMatchingActors(policy, resourceSpec);

      // Step 3: For each matching policy, add actors that are authorized.
      authorizedUsers.addAll(matchingActors.getUsers());
      authorizedGroups.addAll(matchingActors.getGroups());
      if (matchingActors.allUsers()) {
        allUsers = true;
      }
      if (matchingActors.allGroups()) {
        allGroups = true;
      }
    }

    // Step 4: Return all authorized users and groups.
    return new AuthorizedActors(privilege, authorizedUsers, authorizedGroups, allUsers, allGroups);
  }

  /**
   * Invalidates the policy cache and fires off a refresh thread. Should be invoked
   * when a policy is created, modified, or deleted.
   */
  public void invalidateCache() {
    _refreshExecutorService.execute(_policyRefreshRunnable);
  }

  @Override
  public AuthorizationMode mode() {
    return _mode;
  }

  public void setMode(final AuthorizationMode mode) {
    _mode = mode;
  }

  /**
   * Returns true if the request's is coming from the system itself, in which cases
   * the action is always authorized.
   */
  private boolean isSystemRequest(final AuthorizationRequest request, final Authentication systemAuthentication) {
    return systemAuthentication.getActor().toUrnStr().equals(request.actorUrn());
  }

  /**
   * Returns true if a policy grants the requested privilege for a given actor and resource.
   */
  private boolean isRequestGranted(final DataHubPolicyInfo policy, final AuthorizationRequest request) {
    if (AuthorizationMode.ALLOW_ALL.equals(mode())) {
      return true;
    }
    final PolicyEngine.PolicyEvaluationResult result = _policyEngine.evaluatePolicy(
        policy,
        request.actorUrn(),
        request.privilege(),
        request.resourceSpec()
    );
    return result.isGranted();
  }

  /**
   * A {@link Runnable} used to periodically fetch a new instance of the policies Cache.
   *
   * Currently, the refresh logic is not very smart. When the cache is invalidated, we simply re-fetch the
   * entire cache using Policies stored in the backend.
   */
  @VisibleForTesting
  static class PolicyRefreshRunnable implements Runnable {

    private final Authentication _systemAuthentication;
    private final EntityClient _entityClient;
    private final Map<String, List<DataHubPolicyInfo>> _policyCache;

    public PolicyRefreshRunnable(
        final Authentication systemAuthentication,
        final EntityClient entityClient,
        final Map<String, List<DataHubPolicyInfo>> policyCache) {
      _systemAuthentication = systemAuthentication;
      _entityClient = entityClient;
      _policyCache = policyCache;
    }

    @Override
    public void run() {
      try {
        // Populate new cache and swap.
        Map<String, List<DataHubPolicyInfo>> newCache = new HashMap<>();

        int start = 0;
        int count = 30;
        int total = 30;

        while (start < total) {
          try {
            log.debug(String.format("Batch fetching policies. start: %s, count: %s ", start, count));
            final ListUrnsResult policyUrns = _entityClient.listUrns(POLICY_ENTITY_NAME, start, count, _systemAuthentication);
            final Map<Urn, EntityResponse> policyEntities = _entityClient.batchGetV2(POLICY_ENTITY_NAME,
                new HashSet<>(policyUrns.getEntities()), null, _systemAuthentication);

            addPoliciesToCache(newCache, policyEntities.values());

            total = policyUrns.getTotal();
            start = start + count;
          } catch (RemoteInvocationException e) {
            log.error(String.format(
                "Failed to retrieve policy urns! Skipping updating policy cache until next refresh. start: %s, count: %s", start, count), e);
            return;
          }
          synchronized (_policyCache) {
            _policyCache.clear();
            _policyCache.putAll(newCache);
          }
        }
        log.debug(String.format("Successfully fetched %s policies.", total));
      } catch (Exception e) {
        log.error("Caught exception while loading Policy cache. Will retry on next scheduled attempt.", e);
      }
    }

    private void addPoliciesToCache(final Map<String, List<DataHubPolicyInfo>> cache,
        final Collection<EntityResponse> entityResponses) {
      for (final EntityResponse entityResponse : entityResponses) {
        addPolicyToCache(cache, entityResponse);
      }
    }

    private void addPolicyToCache(final Map<String, List<DataHubPolicyInfo>> cache, final EntityResponse entityResponse) {
      EnvelopedAspectMap aspectMap = entityResponse.getAspects();
      if (!aspectMap.containsKey(DATAHUB_POLICY_INFO_ASPECT_NAME)) {
        throw new IllegalArgumentException(
            String.format("Failed to find DataHubPolicyInfo aspect in DataHubPolicy data %s. Invalid state.", aspectMap));
      }
      addPolicyToCache(cache, new DataHubPolicyInfo(aspectMap.get(DATAHUB_POLICY_INFO_ASPECT_NAME).getValue().data()));
    }

    private void addPolicyToCache(final Map<String, List<DataHubPolicyInfo>> cache, final DataHubPolicyInfo policy) {
      final List<String> privileges = policy.getPrivileges();
      for (String privilege : privileges) {
        List<DataHubPolicyInfo> existingPolicies = cache.getOrDefault(privilege, new ArrayList<>());
        existingPolicies.add(policy);
        cache.put(privilege, existingPolicies);
      }
    }
  }

  private List<Urn> userOwners(final Ownership ownership) {
    return ownership.getOwners()
        .stream()
        .filter(owner -> CORP_USER_ENTITY_NAME.equals(owner.getOwner().getEntityType()))
        .map(Owner::getOwner)
        .collect(Collectors.toList());
  }

  private List<Urn> groupOwners(final Ownership ownership) {
    return ownership.getOwners()
        .stream()
        .filter(owner -> CORP_GROUP_ENTITY_NAME.equals(owner.getOwner().getEntityType()))
        .map(Owner::getOwner)
        .collect(Collectors.toList());
  }

  /**
   * Class used to represent all users authorized to perform a particular privilege.
   */
  public static class AuthorizedActors {
    final String _privilege;
    final List<Urn> _users;
    final List<Urn> _groups;
    final Boolean _allUsers;
    final Boolean _allGroups;

    public AuthorizedActors(final String privilege, final List<Urn> users, final List<Urn> groups, final Boolean allUsers, final Boolean allGroups) {
      _privilege = privilege;
      _users = users;
      _groups = groups;
      _allUsers = allUsers;
      _allGroups = allGroups;
    }

    public String getPrivilege() {
      return _privilege;
    }

    public List<Urn> getUsers() {
      return _users;
    }

    public List<Urn> getGroups() {
      return _groups;
    }

    public Boolean allUsers() {
      return _allUsers;
    }

    public Boolean allGroups() {
      return _allGroups;
    }
  }

}
