# CATMS-Backend

Spring Boot backend and MySQL database scripts for MedSync / CATMS.

## Tech Stack
- Java 21 / Spring Boot 3
- Spring JDBC (`JdbcTemplate`, `NamedParameterJdbcTemplate`)
- MySQL 8.0
- Docker & Docker Compose

## Project Structure
```text
CATMS-Backend/
├── database/        # SQL scripts in execution order (01 to 10)
├── src/             # Spring Boot source code
├── compose.yaml     # Docker compose for local dev (MySQL + Backend + Frontend)
├── Dockerfile       # Backend container build
├── pom.xml          # Maven dependencies
└── .env.example     # Sample environment variables
```

## Running the Project

### Option 1: Using Docker (Recommended)
1. Copy the sample environment file:
   ```bash
   cp .env.example .env
   ```
2. Build and start containers:
   ```bash
   docker compose up --build
   ```

Backend will be running on `http://localhost:8080` and MySQL on port `3306`.

### Option 2: Running Locally
1. Start your local MySQL server and create the database by running the scripts in the `database/` folder in order:
   - `01_database.sql`
   - `02_tables.sql`
   - `03_constraints.sql`
   - `04_indexes.sql`
   - `05_views.sql`
   - `06_functions.sql`
   - `07_procedures.sql`
   - `08_triggers.sql`
   - `09_seed_data.sql`
   - `10_tests.sql`

2. Run the Spring Boot application:
   ```bash
   mvn spring-boot:run
   ```
