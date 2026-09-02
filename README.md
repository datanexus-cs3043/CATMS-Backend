# CATMS-Backend

Spring Boot 3 REST API backend and MySQL database layer for **MedSync / CATMS**.

## Technical Stack

- **Language & Runtime**: Java 21 LTS
- **Framework**: Spring Boot 3 (`spring-boot-starter-web`)
- **Data Access**: Spring JDBC (`JdbcTemplate`, `NamedParameterJdbcTemplate`)
- **Database Engine**: MySQL 8.0
- **Containerization**: Docker & Docker Compose

## Repository Structure

```text
CATMS-Backend/
├── database/        # 10-step SQL scripts execution pipeline (01 to 10)
├── src/             # Spring Boot application source code
├── compose.yaml     # Multi-container Docker Compose setup (Database + Backend + Frontend)
├── Dockerfile       # Multi-stage container build definition
├── pom.xml          # Apache Maven dependencies
└── .env.example     # Environment variable configuration template
```

## Execution Guide

### Option 1: Docker Compose (Recommended)

1. Copy environment template:
   ```bash
   cp .env.example .env
   ```
2. Build and start containers:
   ```bash
   docker compose up --build
   ```

The REST API will run on `http://localhost:8080` and MySQL on port `3306`.

### Option 2: Local Execution

1. Start local MySQL 8.0 server and execute SQL scripts in `database/` in exact numeric sequence (`01_database.sql` to `10_tests.sql`).
2. Run the Spring Boot application:
   ```bash
   mvn spring-boot:run
   ```

## Central Documentation

For full database guidelines, transaction handling rules, and system architecture blueprints, visit the **[project-docs Repository](https://github.com/datanexus-cs3043/project-docs)**.
