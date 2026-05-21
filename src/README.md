# Build and start the application

This is a quick guide on how to build and start the application

Notes for development:

- About environments:
  - All virtual environments should be named `.venv`
  - The config files should be named `.env`
  - The .env-files will be added to the repo. This is usually not reccomended. But because this is only a school project with public data, there is no real security risk. Additionally, it makes the hand-in of the project easier.
- About backend:
  - The backend uses a simplified structure due to its limited size

## For Poduction - with docker

1. Adjust the `/backend/.evv` file (if needed):
   1. `POSTGRES_HOST=db`
   2. `MODEL_SERVICE_URL=http://model-service:8001`
2. Adjust the `/frontend/.evv` file (if needed):
   1. `API_URL=http://backend:8001`
3. Open a shell or bash:
   1. Navigate to the ./src directory
   2. run to build and boot:
      1. shell: `docker compose -f docker-compose.db_included.yml up --build`
      2. bash: `docker compose -f docker-compose.db_included.yml up --build`

## For Development - without docker [Legacy]

1. Install and launch PostgreSQL Server
   1. Installation guide: <a href='https://www.postgresql.org/download/'>PostgreSQL Downloads</a><br>Important: Create a user with the following credentials (or change the connection config in ./src/backend/.env if you must):
      1. username: postgres
      2. password: postgres
   2. If not automatically launched, run:
      1. shell: `net start postgresql-x64-18`
      2. bash: `sudo systemctl start postgresql`
   3. Create a database named <i>cinematch</i>
   4. Install the postgres .dump file (see: <a href='https://www.bytebase.com/reference/postgres/how-to/how-to-install-pgdump-on-mac-ubuntu-centos-windows/'>How to install pg_dump on your Mac, Ubuntu, CentOS, Windows</a>)
   5. Adjust the `/backend/.evv` file:
      1. For local use: `POSTGRES_HOST=localhost`
      2. (For docker use: `POSTGRES_HOST=db`)
2. Create and install the local virtual environments as `.venv`:
   1. Setup as:
      1. `.src/backend/.venv/`
      2. `.src/frontend/.venv/`
      3. `.src/model-service/.venv/`
   2. Activate and install the concerning reqruirements with uv

3. Boot the services:
   1. Backend: `run_dev_server.py`
   2. Frontend: `streamlit run main.py`
   3. Model Service: `model-service.py`

4. FsatAPI Docu available at:
   1. Backend <a href="localhost:8000/docs">localhost:8000/docs</a> or <a href="127.0.0.1:8000/docs">127.0.0.1:8000/docs</a>.
   2. Model Service <a href="localhost:8001/docs">localhost:8000/docs</a> or <a href="127.0.0.1:8001/docs">127.0.0.1:8000/docs</a>.

## For Deployment - with Docker

Deployment targets **Google Cloud Run** (fully managed, HTTPS URLs auto-generated). Each service gets a `https://*-xxx.run.app` URL. The CI/CD pipeline is handled by GitHub Actions.

**Prerequisites:** A Google Cloud account with $300 free trial credits and a GitHub account.

### 1. Create GCP project and enable APIs

In [Google Cloud Console](https://console.cloud.google.com):

1. Create a new project (e.g. `cinematch`)
2. Enable the following APIs (APIs & Services → Enable APIs):
   - Cloud Run API
   - Cloud SQL Admin API
   - Artifact Registry API
   - Secret Manager API

### 2. Set up infrastructure (run in Google Cloud Shell)

```bash
PROJECT_ID="$(gcloud config get-value project)"
REGION="europe-west6"   # change to your nearest region

# Artifact Registry (stores Docker images)
gcloud artifacts repositories create cinematch \
  --repository-format=docker \
  --location=$REGION

# Cloud SQL (PostgreSQL 18 database)
gcloud sql instances create cinematch-db \
  --database-version=POSTGRES_18 \
  --edition=ENTERPRISE_PLUS \
  --tier=db-perf-optimized-N-2 \
  --region=$REGION \
  --storage-size=10GB

gcloud sql databases create cinematch --instance=cinematch-db
gcloud sql users create cinematch_user --instance=cinematch-db --password=CHOOSE_A_PASSWORD

# Grant cinematch_user the permissions required by the seed script
gcloud sql connect cinematch-db --user=postgres --project=$PROJECT_ID
# In the psql session run:
#   GRANT cloudsqlsuperuser TO cinematch_user;
# Then \q to exit.

# Note the public IP for the next step:
gcloud sql instances describe cinematch-db --format="value(ipAddresses[0].ipAddress)"
```

### 3. Store secrets in Secret Manager

```bash
# Database connection string — uses Unix socket via Cloud SQL connector (no public IP needed)
# Replace YOUR_PASSWORD, PROJECT_ID, and REGION with your actual values
echo -n "postgresql://cinematch_user:YOUR_PASSWORD@/cinematch?host=/cloudsql/PROJECT_ID:REGION:cinematch-db" \
  | gcloud secrets create DATABASE_URL --data-file=-

# Weights & Biases API key (for model service to download the model)
echo -n "YOUR_WANDB_API_KEY" \
  | gcloud secrets create WANDB_API_KEY --data-file=-
```

> **If `DATABASE_URL` already exists** (e.g. was created with an IP-based URL), add a new version instead:
> ```bash
> echo -n "postgresql://cinematch_user:YOUR_PASSWORD@/cinematch?host=/cloudsql/PROJECT_ID:REGION:cinematch-db" \
>   | gcloud secrets versions add DATABASE_URL --data-file=-
> ```
> Then redeploy by pushing to `main` or triggering the deploy workflow manually so the backend picks up the updated secret.

### 4. Create a GitHub Actions service account

```bash
PROJECT_ID="$(gcloud config get-value project)"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")"

gcloud iam service-accounts create github-actions --display-name="GitHub Actions"
sleep 5   # wait for propagation

SA="github-actions@${PROJECT_ID}.iam.gserviceaccount.com"

for role in roles/run.admin roles/artifactregistry.admin roles/cloudsql.client \
            roles/secretmanager.secretAccessor roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA" --role="$role"
done

# Allow Cloud Run services to read secrets
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Download key — paste the output into GitHub Secret GCP_SA_KEY (do not share elsewhere)
gcloud iam service-accounts keys create key.json --iam-account="$SA"
cat key.json
```

### 5. Add GitHub Secrets and Variables

In the repository → **Settings → Secrets and variables → Actions**:

**Secrets:**

| Name                 | Value                                         |
| -------------------- | --------------------------------------------- |
| `GCP_SA_KEY`         | Full JSON content from `key.json`             |
| `GCP_PROJECT_ID`     | Your GCP project ID (e.g. `cinematch-497011`) |
| `CLOUD_SQL_PASSWORD` | The password chosen in step 2                 |

**Variables** (plain text, not secrets):

| Name                  | Value                                   |
| --------------------- | --------------------------------------- |
| `GCP_REGION`          | e.g. `europe-west6`                     |
| `WANDB_PROJECT`       | W&B project name (e.g. `movie-rec-pyg`) |
| `WANDB_ENTITY`        | W&B username                            |
| `WANDB_ARTIFACT_NAME` | `movie-rec-link-regression-weights`     |
| `CLOUD_SQL_USER`      | `cinematch_user`                        |

### 6. Deploy

Push to `main` — GitHub Actions automatically:

1. Runs `ci.yml`: lints all services and validates Docker builds
2. Runs `deploy.yml`: builds and pushes Docker images to Artifact Registry, then deploys all three services to Cloud Run in order (model-service → backend → frontend), wiring the service URLs together

```bash
git add .
git commit -m "chore: initial deployment"
git push
```

Monitor progress in the repository → **Actions** tab.

### 7. Seed the database (once)

After the first successful deploy, go to **Actions → Seed Database → Run workflow**. This runs `ml_movies_small.sql` against Cloud SQL via the Cloud SQL Auth Proxy (~1–2 min for 147K lines).

**Re-seeding:** If schemas or tables already exist from a previous run, drop and recreate the database first to avoid `already exists` / permission errors:

```bash
gcloud sql connect cinematch-db --user=postgres --project=$PROJECT_ID
```

```sql
DROP DATABASE cinematch;
CREATE DATABASE cinematch;
GRANT ALL PRIVILEGES ON DATABASE cinematch TO cinematch_user;
\q
```

Then re-trigger the workflow.

### 8. Access the app

At the end of the `deploy.yml` run the last step prints the three public URLs:

```
Frontend: https://cinematch-frontend-xxxx-ew.a.run.app   ← open this in your browser
Backend:  https://cinematch-backend-xxxx-ew.a.run.app/docs
Model:    https://cinematch-model-service-xxxx-ew.a.run.app/health
```

> **Note:** The first request after a period of inactivity may take ~30s (Cloud Run cold start while the model service downloads the ONNX model from W&B).

## Shutdown PostgresQL

- shell shutdown postgreSQL: `net stop postgresql-x64-18`
- bash shutdown postgreSQL: `sudo systemctl stop postgresql`
