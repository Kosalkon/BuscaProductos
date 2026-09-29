# DBF Converter / Updater (Windows)

El publicador lee los DBF exclusivamente en modo lectura, crea SQLite y genera actualizaciones verificables. No requiere dependencias de red adicionales.

## Uso durante el desarrollo

```powershell
.\.venv\Scripts\python.exe main.py --force
```

`--force` vuelve a procesar los DBF aunque su fecha o tamaño no hayan cambiado; no crea una versión si la SQLite resultante es idéntica al último snapshot.

Los archivos listos para publicar quedan en `output/`:

- `full-vN.zip`: contiene `products.sqlite` y se usa como recuperación.
- `delta-vN.zip`: contiene un manifiesto y operaciones JSON Lines de alta/baja/modificación.
- `version.json` y `catalog.json`: versión, tamaño, SHA-256, encadenamiento y fecha.

`state/version.json` solo conserva el último estado local. Ambos JSON se escriben de forma atómica. La SQLite se crea primero en un directorio temporal; por lo tanto, un fallo no reemplaza un paquete válido ya publicado.

Para dejar el programa ejecutándose, con comprobación muy liviana de tamaño y fecha de modificación:

```powershell
.\Updater.exe --watch --interval 60
```

En espera no carga la DBF ni hace consultas periódicas a los registros. Solo revisa metadatos de los archivos cada 60 segundos y guarda la última firma localmente, por lo que tampoco reprocesa al reiniciar si las fuentes no cambiaron. El intervalo se puede aumentar en equipos más lentos.

## Configuración

Edite `config/config.json` antes de usar otras fuentes. `product_mapping` indica los nombres reales de los campos DBF; el identificador estable no debe cambiarse una vez que Android utilice la base. Para activar equivalencias, indique el archivo DBF y los campos `product_id` y `code`.

La tabla `products` expone `id`, `internal_code`, `barcode`, `name` y `active`, además de `raw_json` para conservar el registro original sin comprometer la estructura pública. Hay índices para los tres tipos de búsqueda. `equivalents` está preparada para las equivalencias.

## Ejecutable portable

En una PC de desarrollo con Python, ejecute una vez:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --onefile --name Updater --add-data "config;config" main.py
```

El ejecutable resultante es `dist/Updater.exe`. Copie junto a él la carpeta `config` y configure rutas absolutas si los DBF viven en otra ubicación. En la PC de trabajo solo se necesita el `.exe` y su configuración; Python no es necesario.

## Deltas

Se conserva una copia SQLite de referencia en `state/current.sqlite`. Tras la base inicial, cada cambio genera `delta-vN.zip`, que exige `previous_version = N-1`. Sus operaciones son `upsert` o `delete` por ID estable, para `products` y `equivalents`; Android debe verificarlas y aplicarlas en una sola transacción SQLite. Cada 20 versiones (configurable como `updates.full_snapshot_interval`) se vuelve a publicar una base completa para recuperación.

## GitHub Releases

Configure el repositorio y active el publicador en `config/config.json`:

```json
"github": {"enabled": true, "repository": "organizacion/repositorio", "token_file": "secrets.json"}
```

Copie `secrets.example.json` como `secrets.json` junto al ejecutable y pegue el token con permiso de crear releases y cargar assets. El archivo está excluido del proyecto y el token no se escribe en los logs. Manténgalo privado.

Por cada versión se crea primero un Release **borrador**, se cargan el paquete, `version.json` y `catalog.json`, y recién entonces se publica. Si una carga falla, el borrador no queda visible ni reemplaza una actualización válida. Android puede consultar el último Release vía HTTPS, descargar `catalog.json` y elegir una cadena de deltas válida o la última base completa; cada entrada indica el `release_tag` donde vive su archivo.
