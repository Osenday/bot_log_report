Aplicar un *hook* pre-commit con:

```Python
ruff check .
ruff format --check
pytest
```

Esta secuencia ejecuta el análisis estático, confirma el formato y corre las pruebas. Si
una etapa falla, el *hook* o el pipeline deben detenerse.

Referencia [Ruff python](https://academify.com.br/es/ruff-python-calidad-codigo/).