# Defining environment
ARG APP_ENV=prod
ARG BUILDPLATFORM=linux/amd64

FROM alpine:3.14 AS base
ENV DOCKERIZE_VERSION v0.6.1
# Upgrade Alpine and base packages
RUN apk --no-cache --update-cache --available upgrade \
    && if [ $(arch) = "aarch64" ]; then \
       DOCKERIZE_ARCH='aarch64';\
    elif [ $(arch) = "x86_64" ]; then \
      DOCKERIZE_ARCH='amd64'; \
    else \
      echo >&2 "Unsupported architecture $(arch)" ; exit 1; \
    fi \
    && apk --no-cache add tar curl openjdk8-jre bash coreutils gcompat \
    && curl https://repo1.maven.org/maven2/org/eclipse/jetty/jetty-runner/9.4.46.v20220331/jetty-runner-9.4.46.v20220331.jar --output jetty-runner.jar \
    && curl https://repo1.maven.org/maven2/org/eclipse/jetty/jetty-jmx/9.4.46.v20220331/jetty-jmx-9.4.46.v20220331.jar --output jetty-jmx.jar \
    && curl https://repo1.maven.org/maven2/org/eclipse/jetty/jetty-util/9.4.46.v20220331/jetty-util-9.4.46.v20220331.jar --output jetty-util.jar \
    && wget https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v1.4.1/opentelemetry-javaagent-all.jar \
    && wget https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/0.16.1/jmx_prometheus_javaagent-0.16.1.jar -O jmx_prometheus_javaagent.jar \
    && cp /usr/lib/jvm/java-1.8-openjdk/jre/lib/security/cacerts /tmp/kafka.client.truststore.jks \
    && curl -L https://github.com/treff7es/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz | tar -C /usr/local/bin -xzv

FROM --platform=$BUILDPLATFORM alpine:3.14 AS prod-build

# Upgrade Alpine and base packages
RUN apk --no-cache --update-cache --available upgrade \
    && apk --no-cache add openjdk8 perl

COPY . datahub-src
RUN cd datahub-src && ./gradlew :datahub-upgrade:build
RUN cd datahub-src && cp datahub-upgrade/build/libs/datahub-upgrade.jar ../datahub-upgrade.jar

FROM base as prod-install
COPY --from=prod-build /datahub-upgrade.jar /datahub/datahub-upgrade/bin/
COPY --from=prod-build /datahub-src/metadata-models/src/main/resources/entity-registry.yml /datahub/datahub-gms/resources/entity-registry.yml

FROM base as dev-install
# Dummy stage for development. Assumes code is built on your machine and mounted to this image.
# See this excellent thread https://github.com/docker/cli/issues/1134

FROM ${APP_ENV}-install as final

RUN addgroup -S datahub && adduser -S datahub -G datahub
USER datahub

ENTRYPOINT ["java", "-jar", "/datahub/datahub-upgrade/bin/datahub-upgrade.jar"]
