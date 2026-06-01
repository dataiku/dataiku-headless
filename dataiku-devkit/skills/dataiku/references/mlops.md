# Dataiku MLOps — Model Lifecycle & Deployment

Manage the full ML model lifecycle from training through production deployment and monitoring.

## Overview

Dataiku provides an integrated MLOps pipeline:

```
Train → Evaluate → Version → Deploy → Monitor → Retrain
  ↑                                                  |
  └──────────────────────────────────────────────────┘
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **Visual ML** | No-code model training and AutoML |
| **Saved Models** | Versioned model registry |
| **MLflow Integration** | Import custom/external models |
| **Evaluation Store** | Compare model versions |
| **API Node** | Real-time prediction endpoints |
| **Project Deployer** | Promote projects across environments |
| **API Deployer** | Deploy prediction services |

## Visual ML — Training Models

### ML Iteration Cycle

The core ML workflow is an iteration loop:

```
Create ML Task → Configure → Train → Inspect results → Refine → Train → Deploy to Flow → Score
```

Each "train" creates a new training session with multiple model candidates. Iterate on settings (algorithms, features, sampling) between sessions. Once satisfied, deploy one model to the Flow as a saved model.

### Creating a Visual ML Task

```
Flow → Dataset → Lab → AutoML Prediction / Clustering
  → Select target column
  → Choose prediction type (binary, multiclass, regression)
  → Configure features
  → Select algorithms
  → Train
```

An ML Task is identified by its `analysisId` and `mltaskId` — you always need both.

### Updating an Existing Saved Model

When iterating on a deployed model, deploying a new version to the same saved model (via `--saved-model-id` in the `dku-cli` skill) creates a new version while preserving the model's ID and downstream references. Use this instead of creating duplicate saved models on each iteration.

### Forecasting Models

Forecasting needs a time variable (storage type `dateonly` or `date`) and a target variable. If the time column is stored as string, use a Prepare recipe to parse it first. After creation, confirm the forecasting horizon and time step with the user.

### Algorithm Selection Guide

| Task Type | Recommended Algorithms | When to Use |
|-----------|----------------------|-------------|
| **Binary Classification** | XGBoost, LightGBM, Random Forest | Default choice for tabular data |
| **Multiclass** | XGBoost, LightGBM, Logistic Regression | Categorical target with 3+ classes |
| **Regression** | XGBoost, LightGBM, Ridge, Lasso | Numeric target prediction |
| **Clustering** | K-Means, DBSCAN, Hierarchical | Unsupervised grouping |
| **Deep Learning** | Keras (via code) | Image, text, sequence data |

### Feature Engineering (Visual ML)

```
Feature handling options per column:
- Numeric: raw, binning, flag missing, rescaling
- Categorical: dummy encoding, target encoding, ordinal, hashing
- Text: TF-IDF, word hashing, tokenization
- Date: extract components (year, month, day, weekday, hour)
```

## Saved Models — Version Management

### Python API for Saved Models

```python
import dataiku

client = dataiku.api_client()
project = client.get_default_project()

# List saved models
models = project.list_saved_models()
for m in models:
    print(f"{m['name']} (id: {m['id']})")

# Get saved model
sm = project.get_saved_model("model_id")

# List versions
versions = sm.list_versions()
for v in versions:
    print(f"Version: {v['snippet']['trainDate']} - Active: {v.get('active', False)}")

# Get active version
active = sm.get_active_version()
details = active.get_details()
```

### Model Metrics

```python
details = active.get_details()
perf = details.get_performance_metrics()

auc = perf.get("auc")
accuracy = perf.get("accuracy")
f1 = perf.get("f1")
rmse = perf.get("rmse")  # regression
```

### Deploy to Flow

```python
sm.set_active_version(version_id)
```

## MLflow Integration

### Setup MLflow Tracking in DSS

```python
import dataiku
import mlflow

project = dataiku.api_client().get_default_project()
managed_folder = project.get_managed_folder("mlflow_artifacts")

with project.setup_mlflow(managed_folder=managed_folder) as mlflow_handle:
    mlflow_handle.set_experiment("my_experiment")

    with mlflow_handle.start_run(run_name="training_v1") as run:
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=100)
        model.fit(X_train, y_train)

        accuracy = model.score(X_test, y_test)
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_param("n_estimators", 100)
        mlflow.sklearn.log_model(model, "model")
```

### Deploy MLflow Model to Saved Model

```python
mlflow_extension = project.get_mlflow_extension()

classes = list(map(str, model.classes_.tolist()))
mlflow_extension.set_run_inference_info(
    run.info.run_id,
    "BINARY_CLASSIFICATION",
    classes,
    "my_code_environment",
    "target_column_name"
)

mlflow_extension.deploy_run_model(
    run.info.run_id,
    "saved_model_id",
    evaluation_dataset=dataiku.Dataset("test_data")
)
```

## Model Evaluation

### Evaluation Recipe

```python
evaluation_store = project.get_model_evaluation_store("store_id")

evaluation = evaluation_store.run_evaluation(
    model_ref="saved_model_id",
    dataset_ref="evaluation_dataset"
)

results = evaluation.get_results()
```

### Comparing Model Versions

```
Evaluation Store UI:
  → Compare multiple versions side-by-side
  → View metric trends over time
  → Check for performance degradation
  → Identify data drift
```

### Custom Evaluation Metrics

```python
def compute_custom_metrics(model, dataset):
    df = dataiku.Dataset(dataset).get_dataframe()
    predictions = model.predict(df)

    df["predicted"] = predictions
    expected_revenue = df[df["predicted"] == 1]["deal_value"].sum()

    return {
        "expected_revenue": expected_revenue,
        "precision_at_top_100": compute_precision_at_k(df, k=100)
    }
```

## Drift Detection & Monitoring

### Data Drift

```
Model → Monitoring → Data Drift
  → Compare training distribution vs. current data
  → Track feature distributions over time
  → Alert on significant distribution shifts
```

### Performance Monitoring

```python
import dataiku
from sklearn.metrics import accuracy_score, roc_auc_score

project = dataiku.api_client().get_default_project()

scored = dataiku.Dataset("scored_with_actuals").get_dataframe()

current_accuracy = accuracy_score(scored["actual"], scored["predicted"])
current_auc = roc_auc_score(scored["actual"], scored["predicted_proba"])

sm = project.get_saved_model("model_id")
training_auc = sm.get_active_version().get_details().get_performance_metrics()["auc"]

drift = abs(training_auc - current_auc)
if drift > 0.05:
    print(f"Performance drift detected: {drift:.3f} AUC drop")
```

## API Node Deployment

### Architecture

```
DSS Design Node → Project Deployer → Automation Node
                → API Deployer → API Node(s)

API Node: Serves real-time prediction endpoints
  → Low latency (<100ms)
  → Horizontal scaling
  → A/B testing support
  → Load balancing
```

### Creating API Service

```python
project = client.get_project("MY_PROJECT")

api_service = project.create_api_service("prediction_service")

api_service.add_prediction_endpoint(
    endpoint_name="score",
    saved_model_id="model_id"
)

settings = api_service.get_settings()
settings.set_endpoint_settings("score", {
    "modelRef": "model_id",
    "active": True
})
settings.save()
```

### Calling Prediction Endpoints

```python
import requests

response = requests.post(
    "https://api-node.example.com/public/api/v1/prediction_service/score/predict",
    headers={"Authorization": "Bearer <api-key>"},
    json={
        "features": {
            "age": 35,
            "income": 75000,
            "department": "engineering"
        }
    }
)

result = response.json()
prediction = result["result"]["prediction"]
probabilities = result["result"]["probabilities"]
```

### A/B Testing

```
API Service → Endpoint "score":
  ├── Model v3 (70% traffic) — current champion
  └── Model v4 (30% traffic) — challenger

Monitor:
  → Accuracy per version
  → Latency per version
  → Business metrics per version
  → Promote challenger when confident
```

## Project Deployer & Bundles

### Create and Deploy Bundle

```python
# On Design Node
project = client.get_project("MY_PROJECT")
project.create_bundle("v2.1.0")

# On Deployer
deployer = client.get_project_deployer()

deployment = deployer.create_deployment(
    deployment_id="prod-my-project",
    project_key="MY_PROJECT",
    infra_id="production-auto-node",
    bundle_id="v2.1.0"
)

deployment.start()
update = deployment.get_status()
```

### Bundle Workflow

```
Development (Design Node):
  1. Develop features, train models
  2. Test thoroughly
  3. Create bundle: project.create_bundle("v2.1.0")

Staging (Automation Node via Deployer):
  4. Deploy bundle to staging
  5. Run validation scenarios
  6. Verify data pipeline integrity

Production (Automation Node via Deployer):
  7. Promote bundle to production
  8. Monitor scenarios and model performance
  9. Rollback if issues detected
```

## Retraining Automation

### Automated Retrain Scenario

```python
from dataiku.scenario import Scenario
import dataiku

s = Scenario()

# Step 1: Rebuild training data
s.build_dataset("training_features")

# Step 2: Retrain model
s.train_model("prediction_model_id")

# Step 3: Evaluate new version
project = dataiku.api_client().get_default_project()
sm = project.get_saved_model("prediction_model_id")
new_version = sm.list_versions()[0]
metrics = new_version["snippet"]

new_auc = metrics.get("auc", 0)
min_auc = 0.80

# Step 4: Conditional activation
if new_auc >= min_auc:
    sm.set_active_version(new_version["id"])
    print(f"New model activated: AUC={new_auc:.3f}")
    s.build_dataset("scored_output")
else:
    print(f"New model rejected: AUC={new_auc:.3f} < {min_auc}")
```

### Retrain Trigger Strategies

| Strategy | Trigger | Use Case |
|----------|---------|----------|
| **Scheduled** | Time-based (weekly/monthly) | Stable domains, regular data updates |
| **Data-driven** | Dataset change trigger | When new training data arrives |
| **Performance-driven** | Custom Python (drift check) | When model metrics degrade |
| **On-demand** | Manual or API call | Ad-hoc retraining requests |

## Data Quality Rules (DSS 12.6+)

```
Dataset → Settings → Data Quality Rules:
  - Column completeness: "email" must be >99% non-null
  - Value range: "age" must be between 0 and 150
  - Uniqueness: "customer_id" must be unique
  - Regex pattern: "phone" must match pattern
  - Custom SQL: Business rule validation
  - Freshness: Data must be updated within 24h
```

## Best Practices

### Model Training
- **Version everything** — models, datasets, code, and configuration
- **Evaluate on holdout** — never evaluate on training data
- **Track experiments** — use MLflow or DSS experiment tracking
- **Automate feature engineering** — reproducible feature pipelines

### Deployment
- **Use bundles** — never deploy ad-hoc changes to production
- **Stage before prod** — always test on staging first
- **Monitor latency** — API Node response times matter
- **Plan rollback** — keep previous bundle ready

### Monitoring
- **Track data drift** — feature distributions change over time
- **Monitor performance** — compare predictions to actuals
- **Set alerts** — automated notification on metric degradation
- **Schedule retraining** — don't wait for failures
