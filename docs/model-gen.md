# Space Update Model

Whatever system you use to send parking space occupancy updates, it must send json payloads
to your site's `/space/update-state` endpoint.

You must create a subclass of
[`SpaceUpdateBaseModel`](https://joshhubert-dsp.github.io/park-it/reference/space_update/#park_it.models.space_update.SpaceUpdateBaseModel)
for your specific update payload. This subclass is passed to [`build_app()`](reference/build_app.md)
and is used to validate requests that hit the endpoint.

I recommended using the excellent tool
[datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator) to
automatically generate the pydantic model from a real json payload for your system.

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

Here's a working example generated for the car sensor I'm using:
```py title="nwave_parking_sensor.py"
--8<-- "src/park_it/models/nwave_parking_sensor.py"
```