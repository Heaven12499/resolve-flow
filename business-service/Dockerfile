FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml ./
RUN mvn -q -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S resolveflow && adduser -S resolveflow -G resolveflow
WORKDIR /app
COPY --from=build /workspace/target/business-service-0.1.0.jar app.jar
USER resolveflow
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
