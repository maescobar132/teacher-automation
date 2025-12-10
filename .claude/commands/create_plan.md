## Proceso Paso a Paso (Sin Asunciones)

### Paso 1: Crear el Archivo de Plan (`create_plan.md`)

Este archivo es su **instrucción formal** para el asistente de código. Use el siguiente contenido exacto para llenar su archivo en la ruta que usted mencionó:

**Ubicación:** `./claude/commands/create_plan.md`

**Contenido a Guardar en el Archivo:**

````markdown
# INSTRUCCIÓN PARA EL ASISTENTE: Implementar Criterios Manuales Dinámicos

## OBJETIVO
Implementar el argumento de línea de comandos `--manual-criteria` en `run_activity.py` para permitir al usuario especificar qué criterios de la rúbrica deben ser evaluados manualmente en el modo híbrido (`--hybrid`). Esta lista debe **SOBRESCRIBIR** la lista de criterios manuales por defecto.

## ARCHIVOS REQUERIDOS PARA CONTEXTO
- run_activity.py (Script principal que contiene ArgumentParser y la lógica de flujo)
- manual_review.py (Archivo auxiliar que contiene las funciones get_format_criteria y get_auto_full_score_criteria)

## TAREAS Y MODIFICACIONES

### Tarea 1: Asegurar Funciones de Criterios por Defecto (manual_review.py)

**Acción:** Asegúrese de que el archivo `manual_review.py` define estas dos funciones. Si el archivo no existe, debe crearlo.

```python
# manual_review.py

def get_format_criteria():
    """Criterios manuales predeterminados: Referencias y Formato."""
    return ["Referencias", "Formato, ortografía y gramática"]

def get_auto_full_score_criteria():
    """Criterios para revisión automática al 100% (ej. Portada)."""
    return ["Portada"] 
````

### Tarea 2: Modificar ArgumentParser (run\_activity.py)

**Acción:** Añadir el nuevo argumento de línea de comandos en la sección del `ArgumentParser` en `run_activity.py` (cerca del argumento `--hybrid`):

```python
# run_activity.py (Fragmento de código a añadir/modificar)

parser.add_argument(
    '--manual-criteria', 
    nargs='+', # Permite pasar múltiples argumentos (criterios)
    default=None, 
    help='Lista de nombres de criterios a evaluar manualmente. Si se usa, SOBRESCRIBE los criterios manuales por defecto.'
)
```

### Tarea 3: Implementar la Lógica Condicional de Carga (run\_activity.py)

**Acción:** Modificar la lógica dentro del bloque `if args.hybrid:` en `run_activity.py` para priorizar el nuevo *flag* de la CLI. El asistente debe asegurarse de que `get_format_criteria()` y `get_auto_full_score_criteria()` estén correctamente importadas en `run_activity.py`.

```python
# run_activity.py (Fragmento de código dentro de 'if args.hybrid:')

rubric = load_rubric(rubric_path)

# --- LÓGICA DE CARGA DINÁMICA DE CRITERIOS MANUALES ---

if args.manual_criteria:
    # Caso 1: Usar la lista de criterios provista por el usuario (CLI)
    manual_criteria_to_check = args.manual_criteria
    print(f"\n[INFO] Usando criterios manuales explícitos (CLI): {manual_criteria_to_check}")
else:
    # Caso 2: Usar la lista de criterios por defecto (fallback)
    manual_criteria_to_check = get_format_criteria() 
    print(f"\n[INFO] Usando criterios manuales por defecto: {manual_criteria_to_check}")


# Criterios automáticos
auto_criteria = get_auto_full_score_criteria() 

# --------------------------------------------------------
# Continuación de la lógica de filtrado
# --------------------------------------------------------

rubric_criteria_names = [c.get("nombre", "") for c in rubric.get("criterios", [])]

# Filtrar criterios manuales
valid_format_criteria = [c for c in manual_criteria_to_check if c in rubric_criteria_names]

# Filtrar criterios automáticos
valid_auto_criteria = [c for c in auto_criteria if c in rubric_criteria_names]
# ... [El resto del código debe usar valid_format_criteria]
```


