# Manual de Usuario: Teacher-Automation

## Sistema de Retroalimentación Formativa Automatizada para Docentes

---

## Tabla de Contenidos

1. [Introducción al Proyecto](#1-introducción-al-proyecto)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Flujos de Trabajo Disponibles](#3-flujos-de-trabajo-disponibles)
4. [Uso desde la Línea de Comandos](#4-uso-desde-la-línea-de-comandos)
5. [Revisión Secuencial de Entregas](#5-revisión-secuencial-de-entregas)
6. [Generación de PDFs desde JSON](#6-generación-de-pdfs-desde-json)
7. [Configuración del Curso (YAML)](#7-configuración-del-curso-yaml)
8. [Rúbricas](#8-rúbricas)
9. [Prompts del Sistema](#9-prompts-del-sistema)
10. [Generación de Archivos de Salida](#10-generación-de-archivos-de-salida)
11. [Integración con Moodle](#11-integración-con-moodle)
12. [Solución de Problemas Frecuentes](#12-solución-de-problemas-frecuentes)
13. [Buenas Prácticas para Docentes](#13-buenas-prácticas-para-docentes)

---

## 1. Introducción al Proyecto

### 1.1 Propósito

**Teacher-Automation** es un sistema de automatización diseñado para asistir a docentes universitarios, especialmente tutores de programas de posgrado en línea, en la generación de retroalimentación formativa para trabajos estudiantiles.

El sistema utiliza la API de Claude (Anthropic) para analizar entregas de estudiantes, evaluarlas según rúbricas predefinidas y generar retroalimentación personalizada, constructiva y alineada con estándares académicos doctorales.

### 1.2 Problemas que Resuelve

- **Reducción de tiempo de calificación**: Automatiza la evaluación inicial de trabajos escritos y participaciones en foros.
- **Consistencia en la retroalimentación**: Aplica los mismos criterios de evaluación de manera uniforme a todos los estudiantes.
- **Retroalimentación formativa de calidad**: Genera comentarios narrativos que incluyen fortalezas, áreas de mejora y sugerencias concretas.
- **Generación de documentos PDF**: Crea archivos de retroalimentación listos para subir a plataformas LMS como Moodle.
- **Procesamiento por lotes**: Permite evaluar múltiples entregas en una sola ejecución con optimización de costos mediante prompt caching.

### 1.3 Limitaciones Actuales

Es fundamental comprender las limitaciones del sistema para utilizarlo de manera efectiva:

| Limitación | Descripción | Solución |
|------------|-------------|----------|
| **Formato APA no detectable** | El texto extraído de PDF/DOCX pierde información de formato (sangría francesa, tipografía, márgenes). | Utilizar modo híbrido (`--hybrid`) para evaluar manualmente estos criterios. |
| **Portada y elementos visuales** | El sistema no puede verificar visualmente elementos como logos institucionales o diseño de portada. | En modo híbrido, el criterio "Portada" recibe puntaje completo automáticamente si el archivo contiene portada. |
| **Numeración de páginas** | No es posible detectar si las páginas están numeradas correctamente desde el texto plano. | Evaluar manualmente con `--hybrid`. |
| **Documentos escaneados** | PDFs basados en imágenes (escaneados) no pueden extraer texto. | El sistema notificará el error; requiere OCR previo o revisión manual. |
| **Límite de tokens** | Documentos muy extensos (más de ~45,000 palabras) exceden el límite del modelo. | El sistema reportará el error y el documento debe procesarse manualmente. |

---

## 2. Arquitectura del Sistema

### 2.1 Estructura del Proyecto

```
teacher-automation/
├── run_activity.py              # Script principal CLI
├── convert_to_pdf.py            # Utilidad de conversión a PDF
├── generate_grades_summary.py   # Generador de resumen de calificaciones
├── review_submissions.py        # Revisor de entregas
├── run_pdf_feedback.py          # Generador de PDF desde JSON
│
├── src/teacher_automation/
│   ├── config/
│   │   ├── courses/
│   │   │   └── FI08.yml         # Configuración del curso
│   │   ├── prompts/
│   │   │   ├── retroalimentacion_formativa.txt
│   │   │   └── retroalimentacion_foro.txt
│   │   └── rubrics/
│   │       ├── rubric_escrito_uca_ead.json
│   │       ├── rubric_foros_general.json
│   │       ├── rubric_propuesta_objetivos.json
│   │       └── [otras rúbricas...]
│   │
│   ├── grading/
│   │   ├── generate_feedback.py  # Generación de retroalimentación con IA
│   │   ├── grader.py             # Lógica de calificación
│   │   └── feedback.py           # Utilidades de feedback
│   │
│   ├── manual/
│   │   └── manual_review.py      # Módulo de revisión manual/híbrida
│   │
│   ├── output/
│   │   └── pdf_generator.py      # Generador de PDFs
│   │
│   ├── processing/
│   │   ├── extractor.py          # Extractor de contenido
│   │   ├── filenames.py          # Limpieza de nombres de archivo
│   │   ├── filetypes.py          # Detección de tipos de archivo
│   │   └── parser.py             # Parser de documentos (PDF, DOCX, DOC)
│   │
│   ├── moodle/                   # Integración con Moodle (API)
│   └── utils/                    # Utilidades generales
│
├── outputs/                      # JSONs de retroalimentación generados
│   └── <curso>/<unidad>/<actividad>/
│
├── outputs_pdf/                  # PDFs de retroalimentación generados
│   └── <curso>/<unidad>/<actividad>/
│
└── tests/                        # Pruebas automatizadas
```

### 2.2 Descripción de Componentes

| Carpeta/Archivo | Propósito |
|-----------------|-----------|
| `config/courses/` | Archivos YAML que definen cursos, unidades, actividades, rúbricas y prompts asociados. |
| `config/prompts/` | Plantillas de prompts que definen el rol y comportamiento del modelo de IA. |
| `config/rubrics/` | Rúbricas en formato JSON con criterios, niveles y puntajes. |
| `processing/` | Módulos para extracción de texto de PDF/DOCX/DOC y limpieza de nombres de archivo. |
| `grading/` | Lógica principal de generación de retroalimentación usando la API de Claude. |
| `manual/` | Funcionalidad para evaluación híbrida (IA + revisión manual del tutor). |
| `output/` | Generación de PDFs profesionales con la retroalimentación. |
| `outputs/` | Directorio donde se guardan los JSON de retroalimentación. |
| `outputs_pdf/` | Directorio donde se guardan los PDFs generados. |

---

## 3. Flujos de Trabajo Disponibles

### 3.1 Flujo de Evaluación Totalmente Automática

**Ideal para:** Foros, textos breves, trabajos donde el formato visual no es criterio de evaluación.

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Descargar entregas de Moodle (ZIP o directorio)            │
│                          ↓                                      │
│  2. Ejecutar: python run_activity.py --course X --unit N       │
│               --activity X.X --dir ~/Downloads/entregas        │
│                          ↓                                      │
│  3. El sistema:                                                 │
│     • Extrae texto de cada archivo (PDF, DOCX, DOC)            │
│     • Envía texto + rúbrica + instrucciones a Claude           │
│     • Genera retroalimentación JSON para cada estudiante       │
│     • Genera PDFs con tabla de puntajes y comentario narrativo │
│                          ↓                                      │
│  4. Revisar outputs/ y outputs_pdf/                            │
│                          ↓                                      │
│  5. Subir PDFs a Moodle como retroalimentación                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Flujo Híbrido/Manual

**Ideal para:** Trabajos escritos formales donde se evalúa formato APA, sangría francesa, numeración de páginas, referencias con URL/DOI, etc.

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Ejecutar con --hybrid:                                      │
│     python run_activity.py --course FI08 --unit 1 --activity   │
│     1.3 --dir ~/Downloads/entregas --hybrid                    │
│                          ↓                                      │
│  2. Para CADA estudiante:                                       │
│     a) El sistema convierte el archivo a PDF (si es DOCX)      │
│     b) Abre el visor de PDF (evince/okular)                    │
│     c) El tutor revisa formato visual                          │
│     d) El tutor ingresa puntajes manuales para:                │
│        • Formato, ortografía y gramática                        │
│        • Referencias (sangría francesa, APA, URLs)             │
│     e) Claude evalúa los criterios de contenido                │
│     f) Se fusionan puntajes manuales + IA                      │
│                          ↓                                      │
│  3. Se genera JSON y PDF con retroalimentación completa        │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Flujo de Conversión y Revisión Manual de PDFs

**Ideal para:** Cuando solo se necesita revisar visualmente los trabajos sin evaluación automática.

```bash
# Convertir DOCX a PDF para revisión
python convert_to_pdf.py --dir ~/Downloads/entregas

# Los PDFs se generan en el mismo directorio
# El tutor puede abrirlos secuencialmente para revisión
```

### 3.4 Flujo de Generación de PDFs desde JSON Existentes

**Ideal para:** Regenerar PDFs después de ajustar manualmente los JSON de retroalimentación.

```bash
# Generar PDFs desde directorio de JSONs
python run_pdf_feedback.py --input-dir outputs/FI08/unidad_1/actividad_1.1 \
                           --output-dir outputs_pdf/FI08/unidad_1/actividad_1.1
```

---

## 4. Uso desde la Línea de Comandos

### 4.1 Sintaxis General

```bash
python run_activity.py [opciones]
```

### 4.2 Parámetros Disponibles

| Parámetro | Corto | Requerido | Descripción |
|-----------|-------|-----------|-------------|
| `--course` | `-c` | Sí | Código del curso (ej: `FI08`). Debe coincidir con un archivo en `config/courses/`. |
| `--unit` | `-u` | Sí | Número de unidad (entero, ej: `1`, `2`). |
| `--activity` | `-a` | Sí | ID de la actividad (ej: `1.1`, `2.2`). Debe coincidir con el YAML del curso. |
| `--dir` | `-d` | Sí | Ruta al directorio o archivo ZIP con las entregas de estudiantes. |
| `--rename` | - | No | Limpia y renombra archivos antes de procesar (elimina metadatos de Moodle). |
| `--hybrid` | - | No | Activa modo híbrido: evaluación IA + revisión manual de formato. |
| `--model` | - | No | Modelo de Claude a usar. Default: `claude-sonnet-4-20250514`. |
| `--debug` | - | No | Muestra información detallada de depuración. |
| `--no-pdf` | - | No | No generar PDFs de retroalimentación (solo JSON). |

### 4.3 Ejemplos de Uso

#### Evaluación automática básica
```bash
python run_activity.py --course FI08 --unit 1 --activity 1.1 \
                       --dir ~/Downloads/entregas
```

#### Evaluación con renombrado de archivos
```bash
python run_activity.py --course FI08 --unit 1 --activity 1.1 \
                       --dir ~/Downloads/entregas --rename
```

#### Evaluación híbrida para trabajos con formato APA
```bash
python run_activity.py --course FI08 --unit 1 --activity 1.3 \
                       --dir ~/Downloads/escritos --hybrid
```

#### Evaluación de foro (texto plano)
```bash
python run_activity.py --course FI08 --unit 2 --activity 2.1 \
                       --dir ~/Downloads/foros
```

#### Procesamiento desde archivo ZIP
```bash
python run_activity.py --course FI08 --unit 1 --activity 1.1 \
                       --dir ~/Downloads/Entregas_U1A1.zip --rename
```

#### Uso con modelo diferente
```bash
python run_activity.py --course FI08 --unit 1 --activity 1.1 \
                       --dir ~/Downloads/entregas --model claude-3-5-sonnet-20241022
```

### 4.4 Ingreso de Instrucciones

Si las instrucciones de la actividad no están definidas en el YAML del curso, el sistema las solicitará interactivamente:

```
============================================================
INSTRUCCIONES DE LA ACTIVIDAD
============================================================
Pega aquí las instrucciones completas de la actividad tomadas de Moodle.
Cuando termines, presiona Ctrl+D (Linux/Mac) o Ctrl+Z seguido de Enter (Windows).
------------------------------------------------------------

[Pegar instrucciones aquí]
^D
```

---

## 5. Revisión Secuencial de Entregas

El script `review_submissions.py` permite revisar visualmente las entregas de estudiantes junto con su retroalimentación generada, mostrando ambos documentos lado a lado.

### 5.1 Propósito

Este script es útil para:
- **Verificar la calidad** de la retroalimentación generada antes de subirla a Moodle
- **Comparar** el trabajo original del estudiante con los comentarios generados
- **Navegar secuencialmente** por todas las entregas de una actividad
- **Revisión eficiente** con ventanas posicionadas automáticamente lado a lado

### 5.2 Requisitos

Para el posicionamiento automático de ventanas lado a lado (solo X11, no Wayland):

```bash
sudo apt install wmctrl
```

### 5.3 Sintaxis

```bash
python review_submissions.py --input <dir_entregas_pdf> --feedback <dir_retroalimentacion_pdf>
```

### 5.4 Parámetros

| Parámetro | Corto | Descripción |
|-----------|-------|-------------|
| `--input` | `-i` | Directorio con los PDFs de entregas originales de estudiantes |
| `--feedback` | `-f` | Directorio con los PDFs de retroalimentación generados |
| `--start` | - | Comenzar desde el estudiante número N (default: 1) |
| `--input-only` | - | Solo abrir archivos de entrada (sin retroalimentación) |
| `--feedback-only` | - | Solo abrir archivos de retroalimentación |
| `--monitor` | - | Monitor donde mostrar (1=primario, 2=secundario, default: 2) |
| `--debug` | - | Mostrar información de depuración para posicionamiento |

### 5.5 Controles Durante la Revisión

Una vez iniciado el script, se muestran los siguientes controles:

| Tecla | Acción |
|-------|--------|
| `Enter` | Avanzar al siguiente estudiante |
| `b` | Retroceder al estudiante anterior |
| `g <num>` | Ir directamente al estudiante número N |
| `q` | Salir del programa |

### 5.6 Ejemplos de Uso

#### Revisión básica lado a lado
```bash
python review_submissions.py \
    --input ~/Downloads/entregas_pdf \
    --feedback outputs_pdf/FI08/unidad_1/actividad_1.1
```

#### Comenzar desde el estudiante 5
```bash
python review_submissions.py \
    -i ~/Downloads/entregas_pdf \
    -f outputs_pdf/FI08/unidad_1/actividad_1.1 \
    --start 5
```

#### Mostrar en monitor primario
```bash
python review_submissions.py \
    -i ~/Downloads/entregas_pdf \
    -f outputs_pdf/FI08/unidad_1/actividad_1.1 \
    --monitor 1
```

#### Solo revisar retroalimentación (sin entregas)
```bash
python review_submissions.py \
    -i ~/Downloads/entregas_pdf \
    -f outputs_pdf/FI08/unidad_1/actividad_1.1 \
    --feedback-only
```

### 5.7 Flujo de Trabajo Típico

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Procesar entregas con run_activity.py                      │
│     (genera JSONs y PDFs de retroalimentación)                 │
│                          ↓                                      │
│  2. Convertir entregas originales a PDF si son DOCX:           │
│     python convert_to_pdf.py --dir ~/Downloads/entregas        │
│                          ↓                                      │
│  3. Revisar secuencialmente:                                    │
│     python review_submissions.py \                              │
│         -i ~/Downloads/entregas \                               │
│         -f outputs_pdf/FI08/unidad_1/actividad_1.1              │
│                          ↓                                      │
│  4. Para cada estudiante:                                       │
│     • Ventana izquierda: Entrega original                       │
│     • Ventana derecha: Retroalimentación generada               │
│     • Presionar Enter para continuar, 'b' para retroceder       │
│                          ↓                                      │
│  5. Si hay correcciones: editar JSON y regenerar PDF            │
└─────────────────────────────────────────────────────────────────┘
```

### 5.8 Notas sobre Wayland

Si usas Wayland (Ubuntu 22.04+ por defecto), el posicionamiento automático de ventanas no funciona. El script detectará esto y mostrará:

```
Note: Wayland detected - auto window positioning unavailable
  Use Super+Left / Super+Right to tile windows manually
```

Usa los atajos de teclado del sistema para posicionar las ventanas manualmente.

---

## 6. Generación de PDFs desde JSON

El script `run_pdf_feedback.py` permite regenerar documentos PDF de retroalimentación a partir de archivos JSON existentes. Esto es útil cuando se han editado manualmente los JSON o cuando se necesita regenerar los PDFs sin volver a procesar las entregas.

### 6.1 Propósito

Este script es útil para:
- **Regenerar PDFs** después de editar manualmente los archivos JSON de retroalimentación
- **Corregir errores** en la retroalimentación sin reprocesar con la IA
- **Generar resumen de calificaciones** en formato texto
- **Procesar JSON** generados por otros medios o sistemas

### 6.2 Requisitos

El script requiere Pandoc y XeLaTeX para la generación de PDFs:

```bash
sudo apt install pandoc texlive-xetex
```

### 6.3 Sintaxis

```bash
python run_pdf_feedback.py --json_dir <directorio_con_jsons>
```

### 6.4 Parámetros

| Parámetro | Descripción |
|-----------|-------------|
| `--json_dir` | Directorio que contiene los archivos JSON de retroalimentación (requerido) |

### 6.5 Salida Generada

El script genera:

1. **Un PDF por estudiante** con:
   - Encabezado con datos del estudiante
   - Tabla de puntajes por criterio con justificaciones
   - Comentario narrativo completo
   - Resumen para Moodle

2. **Archivo `resumen_calificaciones.txt`** con:
   - Lista alfabética de estudiantes
   - Puntaje total de cada uno

Los archivos se guardan en:
```
outputs_feedback/<curso>/unidad_<n>/actividad_<id>/
├── Estudiante_Nombre.pdf
├── Otro_Estudiante.pdf
└── resumen_calificaciones.txt
```

### 6.6 Ejemplos de Uso

#### Regenerar PDFs de una actividad
```bash
python run_pdf_feedback.py --json_dir outputs/FI08/unidad_1/actividad_1.1
```

#### Procesar JSONs de un directorio personalizado
```bash
python run_pdf_feedback.py --json_dir ~/mis_feedbacks_editados
```

### 6.7 Flujo de Trabajo Típico

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Procesar entregas con run_activity.py                      │
│     (genera JSONs en outputs/)                                  │
│                          ↓                                      │
│  2. Revisar JSONs generados                                     │
│     - Abrir outputs/FI08/unidad_1/actividad_1.1/*.json          │
│     - Editar comentario_narrativo si es necesario               │
│     - Ajustar puntajes o justificaciones                        │
│                          ↓                                      │
│  3. Regenerar PDFs:                                             │
│     python run_pdf_feedback.py \                                │
│         --json_dir outputs/FI08/unidad_1/actividad_1.1          │
│                          ↓                                      │
│  4. Los PDFs actualizados se generan en outputs_feedback/       │
└─────────────────────────────────────────────────────────────────┘
```

### 6.8 Notas Importantes

- El script ignora archivos que comiencen con `_` (como `_resumen_procesamiento.json`)
- Si un JSON está malformado, el script lo reporta y continúa con los demás
- El directorio de salida se crea automáticamente si no existe
- Los PDFs existentes se sobrescriben sin confirmación

---

## 7. Configuración del Curso (YAML)

### 7.1 Ubicación

Los archivos de configuración de cursos se encuentran en:
```
src/teacher_automation/config/courses/<CODIGO_CURSO>.yml
```

### 7.2 Estructura del Archivo YAML

```yaml
curso: FI08
nombre: Diseño Metodológico en Investigación GO
descripcion: >
  Curso del Doctorado en Educación (modalidad en línea). Incluye actividades
  escritas y foros que requieren retroalimentación formativa doctoral.

# Configuración de similitud (Turnitin)
similitud:
  max_permitido: 20      # Máximo % sin penalización
  penalizable_hasta: 49  # Rango de penalización a criterio del tutor
  cero_desde: 50         # % que resulta en calificación cero

unidades:
  - unidad: 1
    nombre: "Unidad 1: Objetivos, muestra y escenario"
    actividades:

      - id: "1.1"
        titulo: "Propuesta de objetivos"
        tipo: escrito                    # escrito | foro
        extraer_texto: true              # true para PDF/DOCX, false para texto plano
        rubrica: "src/teacher_automation/config/rubrics/rubric_propuesta_objetivos.json"
        prompt: "src/teacher_automation/config/prompts/retroalimentacion_formativa.txt"
        instrucciones: |
          [Instrucciones completas de la actividad...]

      - id: "1.2"
        titulo: "Foro: Muestreos cuantitativos y cualitativos"
        tipo: foro
        extraer_texto: false
        rubrica: "src/teacher_automation/config/rubrics/rubric_foros_general.json"
        prompt: "src/teacher_automation/config/prompts/retroalimentacion_foro.txt"
        instrucciones: |
          [Instrucciones del foro...]
```

### 7.3 Campos de Actividad

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | String | Identificador único de la actividad (ej: "1.1", "2.3"). |
| `titulo` | String | Nombre descriptivo de la actividad. |
| `tipo` | String | Tipo de actividad: `escrito` o `foro`. |
| `extraer_texto` | Boolean | `true` para extraer texto de PDF/DOCX, `false` para leer como texto plano. |
| `rubrica` | String | Ruta relativa al archivo JSON de la rúbrica. |
| `prompt` | String | Ruta relativa al archivo de prompt del sistema. |
| `instrucciones` | String | Instrucciones completas de la actividad (opcional si se ingresan manualmente). |

### 7.4 Añadir Nuevas Actividades

1. Editar el archivo YAML del curso
2. Agregar la nueva actividad bajo la unidad correspondiente:

```yaml
      - id: "3.1"
        titulo: "Nueva actividad"
        tipo: escrito
        extraer_texto: true
        rubrica: "src/teacher_automation/config/rubrics/rubric_nueva.json"
        prompt: "src/teacher_automation/config/prompts/retroalimentacion_formativa.txt"
        instrucciones: |
          Instrucciones de la nueva actividad...
```

3. Crear la rúbrica JSON correspondiente si es necesario

### 7.5 Añadir Nuevo Curso

1. Crear archivo `src/teacher_automation/config/courses/<CODIGO>.yml`
2. Seguir la estructura mostrada en 5.2
3. Crear las rúbricas necesarias en `config/rubrics/`

---

## 8. Rúbricas

### 8.1 Formato JSON

Las rúbricas utilizan formato JSON con la siguiente estructura:

```json
{
  "nombre": "Nombre descriptivo de la rúbrica",
  "criterios": [
    {
      "nombre": "Nombre del criterio",
      "maximo": 20,
      "niveles": [
        {
          "score": 20,
          "descripcion": "Descripción del nivel excelente"
        },
        {
          "score": 15,
          "descripcion": "Descripción del nivel bueno"
        },
        {
          "score": 10,
          "descripcion": "Descripción del nivel regular"
        },
        {
          "score": 5,
          "descripcion": "Descripción del nivel deficiente"
        },
        {
          "score": 0,
          "descripcion": "Descripción del nivel nulo"
        }
      ]
    }
  ]
}
```

### 8.2 Ejemplo: Rúbrica para Escrito Formal

```json
{
  "nombre": "Rúbrica para escrito (UCA EaD)",
  "criterios": [
    {
      "nombre": "Portada",
      "maximo": 5,
      "niveles": [
        {"score": 5, "descripcion": "Presenta de 7 a 6 elementos: institución, curso, asignatura, actividad, tutor, alumno y fecha."},
        {"score": 4, "descripcion": "Presenta de 5 a 4 elementos."},
        {"score": 3, "descripcion": "Presenta de 3 a 2 elementos."},
        {"score": 2, "descripcion": "Presenta 1 elemento."},
        {"score": 0, "descripcion": "Ausencia de elementos."}
      ]
    },
    {
      "nombre": "Introducción",
      "maximo": 60,
      "niveles": [
        {"score": 60, "descripcion": "Ideas con fundamento teórico, razonamiento claro..."},
        {"score": 45, "descripcion": "Algunas ideas con fundamento teórico..."},
        {"score": 30, "descripcion": "La mayoría de ideas carecen de fundamento..."},
        {"score": 10, "descripcion": "No presenta fundamento teórico..."},
        {"score": 0, "descripcion": "Presenta cantidad considerable de plagio."}
      ]
    }
  ]
}
```

### 8.3 Criterios que Requieren Revisión Humana

Cuando el texto se extrae de PDF/DOCX, los siguientes criterios **no pueden evaluarse automáticamente** y requieren modo híbrido:

| Criterio | Razón |
|----------|-------|
| Formato, ortografía y gramática | Requiere verificar tipografía, márgenes, justificación visual. |
| Referencias | Requiere verificar sangría francesa, URLs/DOI visibles, formato APA visual. |
| Portada | Requiere verificar elementos visuales (logo, diseño). En modo híbrido se asigna puntaje completo automáticamente. |

### 8.4 Crear Nueva Rúbrica

1. Crear archivo JSON en `src/teacher_automation/config/rubrics/`
2. Seguir la estructura de 6.1
3. Asegurar que los nombres de criterios sean descriptivos
4. Los niveles deben estar ordenados de mayor a menor puntaje
5. Referenciar la rúbrica en el YAML del curso

---

## 9. Prompts del Sistema

### 9.1 Propósito

Los prompts definen el comportamiento y personalidad del modelo de IA al generar retroalimentación. Establecen:
- El rol del tutor
- El tono de comunicación
- La estructura esperada de la respuesta
- Las instrucciones específicas de evaluación

### 9.2 Prompt: Retroalimentación Formativa

**Archivo:** `config/prompts/retroalimentacion_formativa.txt`

**Uso:** Trabajos escritos formales (propuestas, ensayos, reportes)

**Características:**
- Tutor de doctorado en educación
- Tono formativo, claro y respetuoso
- Dirigido usando "tú"
- Estructura: apertura → desarrollo → cierre motivador
- Genera JSON con puntajes, comentario narrativo y resumen para Moodle

### 9.3 Prompt: Retroalimentación de Foro

**Archivo:** `config/prompts/retroalimentacion_foro.txt`

**Uso:** Participaciones en foros de discusión

**Características:**
- Evaluación de aportes conceptuales
- Valora profundidad del análisis
- Considera interacción con compañeros
- Formato narrativo fluido (sin listas artificiales)

### 9.4 Modificar o Crear Prompts

Para crear un nuevo prompt:

1. Crear archivo `.txt` en `src/teacher_automation/config/prompts/`
2. Incluir instrucciones claras sobre:
   - Rol del evaluador
   - Criterios a considerar
   - Tono y estilo
   - Formato de salida esperado (JSON)
3. Referenciar en el YAML del curso

**Estructura recomendada del prompt:**

```
[Definición del rol]
Eres un tutor de [nivel] en [área] que...

[Contexto que recibirá]
Recibirás:
- El texto de la actividad del estudiante
- Una rúbrica con criterios y puntajes

[Tareas a realizar]
Tu tarea es:
1. Analizar...
2. Identificar...
3. Asignar puntajes...

[Formato de salida]
Devuelve la respuesta en formato JSON con esta estructura:
{
  "puntajes": [...],
  "comentario_narrativo": "...",
  "resumen_para_moodle": "..."
}
```

---

## 10. Generación de Archivos de Salida

### 10.1 Estructura de Directorios

```
outputs/
└── FI08/
    └── unidad_1/
        └── actividad_1.1/
            ├── Estudiante_Nombre.json
            ├── Otro_Estudiante.json
            └── _resumen_procesamiento.json

outputs_pdf/
└── FI08/
    └── unidad_1/
        └── actividad_1.1/
            ├── Estudiante_Nombre.pdf
            └── Otro_Estudiante.pdf
```

### 10.2 Estructura del JSON de Retroalimentación

```json
{
  "metadata": {
    "estudiante": "Apellido_Nombre",
    "archivo_original": "Apellido_Nombre_U1A1.docx",
    "fecha_procesamiento": "2025-01-15T10:30:00+00:00",
    "curso": "FI08",
    "unidad": 1,
    "actividad": "1.1",
    "rubrica_usada": "rubric_propuesta_objetivos.json",
    "descripcion_yaml": "Propuesta de objetivos",
    "activity_instructions": "[Instrucciones completas...]",
    "student_text": "[Texto extraído del documento...]"
  },
  "retroalimentacion": {
    "puntajes": [
      {
        "criterio": "Objetivo general",
        "puntaje": 18,
        "maximo": 20,
        "justificacion": "El objetivo general presenta estructura adecuada..."
      }
    ],
    "comentario_narrativo": "María, reconozco tu esfuerzo en la elaboración...",
    "resumen_para_moodle": "Versión breve para Moodle (máx 500 caracteres)..."
  }
}
```

### 10.3 Archivo de Resumen de Procesamiento

El archivo `_resumen_procesamiento.json` contiene:

```json
{
  "fecha": "2025-01-15T10:45:00",
  "curso": "FI08",
  "unidad": 1,
  "actividad": "1.1",
  "descripcion_yaml": "Propuesta de objetivos",
  "activity_instructions": "[Instrucciones...]",
  "rubrica_usada": "rubric_propuesta_objetivos.json",
  "prompt_usado": "retroalimentacion_formativa.txt",
  "directorio_origen": "/home/user/Downloads/entregas",
  "modo_hibrido": false,
  "total": 25,
  "exitosos": 23,
  "fallidos": 2,
  "resultados": [
    {"student": "Apellido_Nombre", "file": "archivo.docx", "success": true, "score": 85},
    {"student": "Otro_Estudiante", "file": "otro.pdf", "success": false, "error": "..."}
  ]
}
```

### 10.4 Interpretación de Calificaciones

- **puntaje**: Puntaje asignado por el modelo (o tutor en modo híbrido)
- **maximo**: Puntaje máximo posible según la rúbrica
- **justificacion**: Explicación del puntaje asignado
- **total**: Suma de todos los puntajes individuales
- **manual: true**: Indica criterios evaluados manualmente (en modo híbrido)

---

## 11. Integración con Moodle

### 11.1 Subir PDFs de Retroalimentación

1. Acceder a la actividad en Moodle
2. Ir a "Ver todas las entregas"
3. Para cada estudiante:
   - Clic en "Calificación"
   - En "Archivos de retroalimentación", subir el PDF correspondiente
   - Ingresar la calificación numérica
   - Guardar cambios

### 11.2 Usar el Campo `resumen_para_moodle`

El campo `resumen_para_moodle` del JSON contiene una versión breve (máximo 500 caracteres) del comentario narrativo, ideal para:

- Pegarlo en el campo "Comentarios de retroalimentación" de Moodle
- Enviarlo como mensaje al estudiante
- Incluirlo en notificaciones automáticas

### 11.3 Subida en Lote (Retroalimentación Masiva)

Para subir retroalimentación de múltiples estudiantes:

1. En "Ver todas las entregas", seleccionar "Descargar todas las entregas"
2. Moodle genera un ZIP con estructura específica
3. Añadir los PDFs de retroalimentación en las carpetas correspondientes
4. Resubir el ZIP mediante "Subir múltiples archivos de retroalimentación"

**Nota:** Los nombres de archivo deben coincidir con el formato de Moodle: `Nombre Apellido_ID_assignsubmission_file_*.pdf`

### 11.4 Generación de Resumen CSV

```bash
python generate_grades_summary.py --input-dir outputs/FI08/unidad_1/actividad_1.1 \
                                  --output my_grades.csv
```

Este CSV puede importarse a Moodle mediante "Importar calificaciones".

---

## 12. Solución de Problemas Frecuentes

### 12.1 Problemas de Codificación/Unicode

**Síntoma:** Caracteres extraños en nombres de archivo o texto (mojibake).

**Solución:**
- Usar `--rename` para limpiar nombres de archivo automáticamente
- El sistema intenta múltiples codificaciones: UTF-8, Latin-1, CP1252
- Si persiste, verificar la codificación original del archivo

```bash
python run_activity.py --course FI08 --unit 1 --activity 1.1 \
                       --dir ~/Downloads/entregas --rename
```

### 12.2 Rúbricas Mal Formadas

**Síntoma:** Error al cargar la rúbrica JSON.

**Solución:**
- Validar el JSON con un validador en línea
- Verificar que todos los criterios tengan `nombre`, `maximo` y `niveles`
- Asegurar que `niveles` sea un array de objetos con `score` y `descripcion`

```bash
python -c "import json; json.load(open('src/teacher_automation/config/rubrics/mi_rubrica.json'))"
```

### 12.3 Error con ANTHROPIC_API_KEY

**Síntoma:** `RuntimeError: ANTHROPIC_API_KEY no está definido`

**Solución:**
1. Obtener API key de https://console.anthropic.com/
2. Configurar variable de entorno:

```bash
# Linux/Mac (añadir a ~/.bashrc o ~/.zshrc)
export ANTHROPIC_API_KEY='sk-ant-api03-...'

# O crear archivo .env en el directorio del proyecto
echo "ANTHROPIC_API_KEY=sk-ant-api03-..." > .env
```

### 12.4 Errores en Extracción de Texto

**Síntoma:** "El archivo está vacío o no se pudo extraer texto"

**Causas y soluciones:**

| Causa | Solución |
|-------|----------|
| PDF escaneado (imagen) | Usar OCR previo o evaluar manualmente |
| PDF protegido | Desproteger el PDF |
| DOCX corrupto | Pedir al estudiante que reenvíe |
| Archivo muy pequeño | Verificar que el archivo tenga contenido |

### 12.5 Errores al Renombrar Archivos

**Síntoma:** Conflicto de nombres o archivos no renombrados.

**Solución:**
- Revisar `rename_log.txt` generado en el directorio
- Verificar permisos de escritura
- Si hay duplicados, el sistema añade sufijos `_2`, `_3`, etc.

### 12.6 Depuración con --debug

```bash
python run_activity.py --course FI08 --unit 1 --activity 1.1 \
                       --dir ~/Downloads/entregas --debug
```

El modo debug muestra:
- Tamaño del prompt enviado
- Respuesta cruda del modelo
- Errores de parseo detallados
- Trazas de excepciones completas

### 12.7 Documento Demasiado Grande

**Síntoma:** `DocumentTooLargeError: Documento demasiado grande`

**Solución:**
- El límite es aproximadamente 180,000 tokens (~45,000 palabras)
- Dividir el documento o evaluar manualmente
- Verificar que el documento no contenga imágenes codificadas en base64

---

## 13. Buenas Prácticas para Docentes

### 13.1 Redactar Retroalimentación Efectiva

Al revisar y ajustar la retroalimentación generada:

- **Personalizar el saludo:** Verificar que use el nombre correcto del estudiante
- **Ser específico:** Referenciar partes concretas del trabajo
- **Equilibrar fortalezas y mejoras:** No solo señalar errores
- **Dar acciones concretas:** "Considera añadir X" en lugar de "Falta algo"
- **Mantener tono doctoral:** Profesional pero cercano

### 13.2 Validar Coherencia Rúbrica-Instrucciones

Antes de procesar una actividad:

1. Revisar que la rúbrica cubra todos los aspectos de las instrucciones
2. Verificar que los puntajes máximos sumen 100 (o el total deseado)
3. Confirmar que los niveles de la rúbrica sean progresivos
4. Validar que las descripciones de niveles sean claras y diferenciables

### 13.3 Organizar Flujos de Calificación Semanales

**Flujo sugerido:**

```
Lunes: Descargar entregas de Moodle
       └─> Crear directorio ~/Calificaciones/Semana_XX/

Martes: Procesar con teacher-automation
        └─> python run_activity.py ... --rename

Miércoles: Revisar outputs/ y ajustar si es necesario
           └─> Editar JSONs manualmente si se requiere

Jueves: Regenerar PDFs si hubo cambios
        └─> Subir a Moodle

Viernes: Verificar que todos los estudiantes recibieron retroalimentación
```

### 13.4 Aprovechar el Modo Híbrido

El modo híbrido es especialmente útil cuando:

- La actividad tiene criterios de formato APA estrictos
- Se evalúa calidad visual (gráficos, tablas, presentación)
- Se requiere verificar URLs o DOI funcionales
- El tutor desea añadir comentarios personalizados específicos

**Proceso recomendado:**

1. Preparar lista de verificación para criterios manuales
2. Tener rúbrica impresa o en segunda pantalla
3. Usar atajos de teclado para navegar entre estudiantes
4. Ingresar comentarios breves que el sistema pulirá automáticamente

### 13.5 Respaldo y Versionado

- Mantener copia de los JSONs originales antes de editar
- Usar Git para versionar cambios en rúbricas y prompts
- Documentar modificaciones significativas

```bash
# Respaldar outputs antes de regenerar
cp -r outputs/FI08/unidad_1 outputs/FI08/unidad_1_backup_$(date +%Y%m%d)
```

---

## Anexo: Referencia Rápida de Comandos

```bash
# Evaluación automática básica
python run_activity.py -c FI08 -u 1 -a 1.1 -d ~/entregas

# Con renombrado de archivos
python run_activity.py -c FI08 -u 1 -a 1.1 -d ~/entregas --rename

# Modo híbrido (formato APA)
python run_activity.py -c FI08 -u 1 -a 1.3 -d ~/entregas --hybrid

# Solo generar JSON (sin PDF)
python run_activity.py -c FI08 -u 1 -a 1.1 -d ~/entregas --no-pdf

# Con depuración
python run_activity.py -c FI08 -u 1 -a 1.1 -d ~/entregas --debug

# Generar PDFs desde JSONs existentes
python run_pdf_feedback.py --json_dir outputs/FI08/unidad_1/actividad_1.1

# Revisar entregas y retroalimentación lado a lado
python review_submissions.py -i ~/entregas_pdf -f outputs_pdf/FI08/unidad_1/actividad_1.1

# Generar resumen de calificaciones
python generate_grades_summary.py --input-dir outputs/FI08/unidad_1/actividad_1.1

# Convertir DOCX a PDF
python convert_to_pdf.py --dir ~/Downloads/entregas
```

---

**Teacher-Automation** - Sistema de Retroalimentación Formativa Automatizada
Versión del manual: 1.0
Última actualización: Diciembre 2025
