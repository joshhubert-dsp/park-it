# Generating the Space Update Model

You must create a subclass of `SpaceUpdateBaseModel` for the update payload of the
specific car sensor you are deploying. This subclass is passed to `build_app()`
and is used to automatically validate payloads that hit the `space/update-state` endpoint.

It is recommended to use the excellent tool
[datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator) to
automatically generate the pydantic model from a json payload.

I like running it with these options:
```bash
datamodel-codegen \
--input "your-update-payload.json" \
--input-file-type json \
--output "your_update_class.py" \
--class-name "YourUpdateClass" \
--output-model-type pydantic_v2.BaseModel \
--target-python-version 3.13 \
--use-standard-collections \
--use-union-operator \
--reuse-model \
--use-double-quotes \
--enum-field-as-literal all \
--use-one-literal-as-default \
--collapse-root-models \
--wrap-string-literal \
--disable-timestamp
```

Here's a working example for the car sensor I'm using:
```py title="nwave_parking_sensor.py"
--8<-- "src/park_it/models/nwave_parking_sensor.py"
```