Here's a comprehensive guide to setting up Apache Airflow locally for your ML pipeline.

## Architecture OverviewHere's a complete breakdown of the setup.

---

## 1. Project structure

```
ml-pipeline/
├── dags/
│   └── ml_pipeline_dag.py       # The DAG definition
├── scripts/
│   ├── transform.py             # Data transformation → CSV
│   ├── train.py                 # PyTorch Geometric training
│   └── export_and_push.py      # W&B push + ONNX export
├── model-service/               # Your Cloud Run app
│   ├── Dockerfile
│   └── app.py
├── docker-compose.yaml          # Airflow local setup
├── requirements.txt             # DAG/task dependencies
└── .env                         # Secrets (gitignored)
```

---

## 2. Local Airflow with Docker Compose

The easiest reproducible setup uses the official Airflow Docker Compose file. Create `docker-compose.yaml`:

```yaml
# Fetch the official base and extend it
version: '3.8'

x-airflow-common: &airflow-common
  image: apache/airflow:2.9.1
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
    # Secrets — sourced from .env
    CLOUD_SQL_CONN_STRING: ${CLOUD_SQL_CONN_STRING}
    WANDB_API_KEY: ${WANDB_API_KEY}
    GCP_PROJECT: ${GCP_PROJECT}
    GCP_REGION: ${GCP_REGION}
    CLOUD_RUN_SERVICE: ${CLOUD_RUN_SERVICE}
    ARTIFACT_REGISTRY: ${ARTIFACT_REGISTRY}
  volumes:
    - ./dags:/opt/airflow/dags
    - ./scripts:/opt/airflow/scripts
    - ./model-service:/opt/airflow/model-service
    - /var/run/docker.sock:/var/run/docker.sock  # needed for docker build in tasks
    - ~/.config/gcloud:/home/airflow/.config/gcloud:ro  # gcloud credentials
  depends_on:
    postgres:
      condition: service_healthy

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 5s
      retries: 5

  airflow-init:
    <<: *airflow-common
    command: >
      bash -c "airflow db migrate && airflow users create
        --username admin --password admin
        --firstname Admin --lastname User
        --role Admin --email admin@example.com"

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
```

**First-time setup:**
```bash
echo "AIRFLOW_UID=$(id -u)" >> .env
docker compose up airflow-init
docker compose up -d
# UI at http://localhost:8080 (admin/admin)
```

---

## 3. The DAG (`dags/ml_pipeline_dag.py`)

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import subprocess, os

default_args = {
    "owner": "ml-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="ml_pipeline",
    default_args=default_args,
    schedule="0 3 * * *",  # Daily at 03:00
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ml", "training"],
) as dag:

    def read_from_cloud_sql(**ctx):
        import sqlalchemy, pandas as pd
        engine = sqlalchemy.create_engine(os.environ["CLOUD_SQL_CONN_STRING"])
        df = pd.read_sql("SELECT * FROM your_table", engine)
        df.to_parquet("/tmp/raw_data.parquet", index=False)

    def transform_and_export(**ctx):
        import subprocess
        subprocess.run(
            ["python", "/opt/airflow/scripts/transform.py",
             "--input", "/tmp/raw_data.parquet",
             "--output", "/tmp/processed.csv"],
            check=True
        )

    def retrain_model(**ctx):
        subprocess.run(
            ["python", "/opt/airflow/scripts/train.py",
             "--data", "/tmp/processed.csv",
             "--output", "/tmp/model.pt"],
            check=True
        )

    def push_and_export(**ctx):
        subprocess.run(
            ["python", "/opt/airflow/scripts/export_and_push.py",
             "--model", "/tmp/model.pt",
             "--onnx-out", "/tmp/model.onnx"],
            check=True
        )

    def rebuild_cloud_run(**ctx):
        project = os.environ["GCP_PROJECT"]
        region  = os.environ["GCP_REGION"]
        service = os.environ["CLOUD_RUN_SERVICE"]
        registry = os.environ["ARTIFACT_REGISTRY"]
        image = f"{registry}/{project}/model-service:latest"

        # Copy new ONNX into service directory
        subprocess.run(["cp", "/tmp/model.onnx", "/opt/airflow/model-service/model.onnx"], check=True)

        # Build and push
        subprocess.run(["docker", "build", "-t", image, "/opt/airflow/model-service"], check=True)
        subprocess.run(["docker", "push", image], check=True)

        # Deploy to Cloud Run
        subprocess.run([
            "gcloud", "run", "deploy", service,
            "--image", image,
            "--region", region,
            "--project", project,
            "--platform", "managed",
            "--quiet"
        ], check=True)

    t1 = PythonOperator(task_id="read_from_cloud_sql",    python_callable=read_from_cloud_sql)
    t2 = PythonOperator(task_id="transform_and_export",   python_callable=transform_and_export)
    t3 = PythonOperator(task_id="retrain_model",          python_callable=retrain_model)
    t4 = PythonOperator(task_id="push_and_export_onnx",   python_callable=push_and_export)
    t5 = PythonOperator(task_id="rebuild_cloud_run",      python_callable=rebuild_cloud_run)

    t1 >> t2 >> t3 >> t4 >> t5
```

---

## 4. Key script snippets

**`scripts/export_and_push.py`** — W&B + ONNX:
```python
import wandb, torch, argparse
from your_model import MyGNNModel  # your PyG model class

parser = argparse.ArgumentParser()
parser.add_argument("--model"); parser.add_argument("--onnx-out")
args = parser.parse_args()

model = MyGNNModel()
model.load_state_dict(torch.load(args.model))
model.eval()

# Push to W&B
run = wandb.init(project="your-project", job_type="model-export")
artifact = wandb.Artifact("gnn-model", type="model")
artifact.add_file(args.model)
run.log_artifact(artifact)

# Export ONNX
dummy_input = torch.randn(1, your_input_dim)
torch.onnx.export(model, dummy_input, args.onnx_out, opset_version=17)
run.finish()
print(f"ONNX saved to {args.onnx_out}")
```

---

## 5. Portability — committing config to your repo

Everything needed to reproduce the environment on a new machine lives in the repo. The only thing **not** committed is `.env` (secrets).

**`.env.example`** (commit this):
```bash
CLOUD_SQL_CONN_STRING=postgresql://user:pass@host/db
WANDB_API_KEY=your_key_here
GCP_PROJECT=your-gcp-project
GCP_REGION=europe-west1
CLOUD_RUN_SERVICE=model-service
ARTIFACT_REGISTRY=europe-west1-docker.pkg.dev
```

**New machine setup** is then just:
```bash
git clone your-repo && cd your-repo
cp .env.example .env && nano .env   # fill in real values
echo "AIRFLOW_UID=$(id -u)" >> .env
gcloud auth configure-docker europe-west1-docker.pkg.dev
docker compose up airflow-init
docker compose up -d
```

---

## 6. A few things to watch out for

**PyTorch Geometric in the Airflow container** — the base Airflow image is CPU-only and won't have PyG. You have two options:

- **Extend the image** — create a custom `Dockerfile.airflow` that installs torch + PyG, then point `docker-compose.yaml` to `build: .` instead of the `image:` line. More self-contained.
- **Run training in its own container** — use `DockerOperator` instead of `PythonOperator` for the training task, pointing to a pre-built PyG image. Cleaner separation, especially if you need GPU.

**Docker-in-Docker for the Cloud Run rebuild** — mounting `/var/run/docker.sock` works but means Airflow's container can run `docker build` using the host daemon. This is fine for local dev but be aware of the security implications.

**GCP credentials** — the `~/.config/gcloud` volume mount passes your local `gcloud auth` session into the container. Make sure you've run `gcloud auth login` and `gcloud auth configure-docker` on the host before starting Airflow.