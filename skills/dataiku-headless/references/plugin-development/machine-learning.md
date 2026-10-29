# Visual ML Plugin Extensions

Start with [Plugin development](../plugin-development.md). Check dependencies in the
environments used for training and scoring, along with the deployment options
supported by your Dataiku version.

## Prediction Algorithms

Use generated `algo.json` and `algo.py`, following the
[prediction-algorithm tutorial](https://developer.dataiku.com/latest/tutorials/plugins/prediction-algorithm/ml-algo/index.html).
The descriptor defines prediction types, hyperparameters, and grid search settings. For the
scikit-learn-compatible interface, derive from `BaseCustomPredictionAlgorithm` and
implement `get_clf()` with a matching estimator.

Test training, predictions, probabilities where supported, parameter conversion,
and saving and loading the estimator.
In Dataiku, train, inspect metrics, and score with the saved model before claiming
support for a deployment or export mode.

## Feature Preprocessors

Use `python-preprocessors/<component-id>/preprocessor.json` and `preprocessor.py`,
following the [preprocessor reference](https://doc.dataiku.com/dss/latest/plugins/reference/ml-preprocessors.html).
Declare supported feature types and implement `CustomPreprocessor`. Learn statistics
in `fit`; reuse them in `transform` during scoring. Keep names, dimensionality, and
row alignment stable.

Test unseen categories, nulls, constant inputs, and whether saved models retain the
preprocessor's fitted state. These
components run in the model's process, not a dedicated plugin environment. Verify
training and subsequent scoring, and consult the reference's export limitations.
