"""
Generación de retroalimentación formativa usando Claude.

Este módulo proporciona funciones para generar retroalimentación
automatizada de trabajos estudiantiles usando el API de Anthropic.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os

from ..utils.logging import get_logger

logger = get_logger(__name__)


# Output schema that the LLM must produce
OUTPUT_SCHEMA = """{
  "puntajes": [
    {
      "criterio": "string - nombre del criterio evaluado",
      "puntaje": "number - puntaje obtenido",
      "maximo": "number - puntaje máximo posible",
      "justificacion": "string - explicación del puntaje asignado"
    }
  ],
  "comentario_narrativo": "string - retroalimentación formativa detallada con apertura, desarrollo y cierre",
  "resumen_para_moodle": "string - versión breve (máximo 500 caracteres) para mostrar en Moodle"
}"""


def load_rubric(rubric_path: Path) -> dict[str, Any]:
    """
    Carga una rúbrica desde un archivo JSON.

    Args:
        rubric_path: Ruta al archivo JSON de la rúbrica

    Returns:
        Diccionario con la estructura de la rúbrica

    Raises:
        FileNotFoundError: Si el archivo no existe
        json.JSONDecodeError: Si el JSON no es válido
    """
    logger.debug(f"Cargando rúbrica desde: {rubric_path}")
    with rubric_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt_template(prompt_path: Path) -> str:
    """
    Carga una plantilla de prompt desde un archivo de texto.

    Args:
        prompt_path: Ruta al archivo TXT del prompt

    Returns:
        Contenido del archivo como string

    Raises:
        FileNotFoundError: Si el archivo no existe
    """
    logger.debug(f"Cargando plantilla de prompt desde: {prompt_path}")
    with prompt_path.open("r", encoding="utf-8") as f:
        return f.read()


def build_prompt(
    prompt_template: str,
    rubric: dict[str, Any],
    student_text: str,
    activity_instructions: str | None = None,
    descripcion_yaml: str | None = None,
) -> str:
    """
    Construye el prompt completo para enviar a Claude.

    Args:
        prompt_template: Plantilla base del prompt
        rubric: Diccionario con la rúbrica
        student_text: Texto del estudiante a evaluar
        activity_instructions: Instrucciones de la actividad proporcionadas por el tutor
        descripcion_yaml: Descripción de la actividad desde el archivo YAML

    Returns:
        Prompt completo listo para enviar al modelo
    """
    rubric_json = json.dumps(rubric, ensure_ascii=False, indent=2)

    parts = [prompt_template, ""]

    if activity_instructions:
        parts.append(f"Instrucciones de la actividad:\n\"\"\"\n{activity_instructions}\n\"\"\"\n")

    if descripcion_yaml:
        parts.append(f"Descripción de la actividad (YAML):\n\"\"\"\n{descripcion_yaml}\n\"\"\"\n")

    parts.append(f"Rúbrica (formato JSON):\n{rubric_json}\n")
    parts.append(f"Texto del estudiante:\n\"\"\"\n{student_text}\n\"\"\"\n")

    # Add strict output schema instructions
    parts.append("=" * 60)
    parts.append("FORMATO DE SALIDA OBLIGATORIO")
    parts.append("=" * 60)
    parts.append("""
IMPORTANTE: Debes producir ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta.
NO incluyas ningún campo adicional. NO incluyas total_score, grading_summary, detailed_rubric,
model_parameters, model_raw_response, token usage, ni ningún otro campo no especificado.

ESQUEMA DE SALIDA:
""")
    parts.append(OUTPUT_SCHEMA)
    parts.append("""
REGLAS:
1. El JSON debe ser válido y parseable directamente.
2. Cada criterio de la rúbrica debe tener una entrada en "puntajes".
3. "puntaje" debe ser un número (no string).
4. "maximo" debe ser el puntaje máximo posible para ese criterio según la rúbrica.
5. "justificacion" debe explicar específicamente por qué se asignó ese puntaje.
6. "comentario_narrativo" debe ser formativo, constructivo y personalizado.
7. "resumen_para_moodle" debe ser conciso (máximo 500 caracteres).
8. NO incluyas bloques de código markdown (```json) alrededor del JSON.
9. NO incluyas texto explicativo antes o después del JSON.

Devuelve SOLO el JSON, sin texto adicional antes o después.
""")

    return "\n".join(parts)


def extract_json_from_response(raw_text: str) -> dict[str, Any]:
    """
    Extrae y parsea JSON de la respuesta del modelo.

    Intenta extraer JSON incluso si viene envuelto en bloques de código
    o tiene texto adicional.

    Args:
        raw_text: Texto crudo de la respuesta

    Returns:
        Diccionario parseado del JSON

    Raises:
        ValueError: Si no se puede extraer JSON válido
    """
    text = raw_text.strip()

    # Intento 1: Parsear directamente
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Intento 2: Buscar JSON en bloques de código markdown
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    matches = re.findall(code_block_pattern, text)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Intento 3: Buscar objeto JSON con regex
    json_pattern = r"\{[\s\S]*\}"
    matches = re.findall(json_pattern, text)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"No se pudo extraer JSON válido de la respuesta:\n{text[:500]}...")


def validate_feedback_structure(data: dict[str, Any]) -> None:
    """
    Valida que el JSON de retroalimentación tenga la estructura esperada.

    Args:
        data: Diccionario a validar

    Raises:
        ValueError: Si faltan campos requeridos o tienen tipos incorrectos
    """
    required_keys = ["puntajes", "comentario_narrativo", "resumen_para_moodle"]

    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        raise ValueError(
            f"El JSON devuelto no contiene las claves requeridas: {missing_keys}. "
            f"Claves presentes: {list(data.keys())}"
        )

    # Validar tipos de campos de texto
    if not isinstance(data["comentario_narrativo"], str):
        raise ValueError("El campo 'comentario_narrativo' debe ser un string")

    if not isinstance(data["resumen_para_moodle"], str):
        raise ValueError("El campo 'resumen_para_moodle' debe ser un string")

    # Validar estructura de puntajes
    if not isinstance(data["puntajes"], list):
        raise ValueError("El campo 'puntajes' debe ser una lista")

    if len(data["puntajes"]) == 0:
        raise ValueError("El campo 'puntajes' no puede estar vacío")

    puntaje_required_keys = ["criterio", "puntaje", "maximo", "justificacion"]

    for i, puntaje in enumerate(data["puntajes"]):
        if not isinstance(puntaje, dict):
            raise ValueError(f"Cada puntaje debe ser un diccionario (índice {i})")

        missing_puntaje_keys = [k for k in puntaje_required_keys if k not in puntaje]
        if missing_puntaje_keys:
            raise ValueError(
                f"Puntaje en índice {i} no contiene las claves requeridas: {missing_puntaje_keys}"
            )

        # Validar tipos
        if not isinstance(puntaje["criterio"], str):
            raise ValueError(f"'criterio' debe ser string (índice {i})")
        if not isinstance(puntaje["puntaje"], (int, float)):
            raise ValueError(f"'puntaje' debe ser un número (índice {i})")
        if not isinstance(puntaje["maximo"], (int, float)):
            raise ValueError(f"'maximo' debe ser un número (índice {i})")
        if not isinstance(puntaje["justificacion"], str):
            raise ValueError(f"'justificacion' debe ser string (índice {i})")


def _call_llm_for_feedback(
    client: Any,
    full_prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """
    Llama al API de Anthropic y retorna el texto de la respuesta.

    Args:
        client: Cliente de Anthropic
        full_prompt: Prompt completo a enviar
        model: Modelo a usar
        max_tokens: Máximo de tokens
        temperature: Temperatura para generación

    Returns:
        Texto crudo de la respuesta
    """
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {
                "role": "user",
                "content": full_prompt,
            }
        ],
    )

    content_blocks = response.content
    text_parts = []
    for block in content_blocks:
        if block.type == "text":
            text_parts.append(block.text)

    return "".join(text_parts).strip()


def _build_json_fix_prompt(malformed_json: str, error_message: str) -> str:
    """
    Construye un prompt para corregir JSON malformado.

    Args:
        malformed_json: El JSON que falló al parsear
        error_message: El mensaje de error del parser

    Returns:
        Prompt para solicitar corrección del JSON
    """
    return f"""El siguiente JSON tiene errores y no se puede parsear:

```
{malformed_json[:2000]}
```

Error: {error_message}

Por favor, corrige el JSON para que sea válido y siga exactamente este esquema:

{OUTPUT_SCHEMA}

IMPORTANTE:
- Devuelve SOLO el JSON corregido, sin explicaciones.
- NO incluyas bloques de código markdown.
- Asegúrate de que todos los strings estén correctamente escapados.
- Asegúrate de que todos los números sean valores numéricos (no strings).
"""


def generate_feedback_for_text(
    student_text: str,
    rubric_path: Path,
    prompt_path: Path,
    estudiante: str,
    archivo_original: str,
    curso: str,
    unidad: int,
    actividad: str,
    activity_instructions: str | None = None,
    descripcion_yaml: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    output_base_path: Path | None = None,
) -> dict[str, Any]:
    """
    Genera retroalimentación formativa para un texto estudiantil.

    Esta función:
    1. Carga la rúbrica y el template del prompt
    2. Construye el prompt completo con el esquema de salida requerido
    3. Llama al API de Anthropic
    4. Parsea y valida la respuesta JSON (con reintentos si es necesario)
    5. Construye el JSON final con metadata y retroalimentacion
    6. Opcionalmente guarda el resultado en el path especificado

    Args:
        student_text: Texto del estudiante a evaluar
        rubric_path: Ruta al archivo JSON de la rúbrica
        prompt_path: Ruta al archivo TXT del prompt de retroalimentación
        estudiante: Nombre o identificador del estudiante
        archivo_original: Nombre del archivo original entregado
        curso: Código o nombre del curso
        unidad: Número de unidad
        actividad: Identificador de la actividad
        activity_instructions: Instrucciones de la actividad proporcionadas por el tutor
        descripcion_yaml: Descripción de la actividad desde archivo YAML
        model: Modelo de Claude a usar
        max_tokens: Máximo de tokens en la respuesta
        temperature: Temperatura para la generación (0.0-1.0)
        output_base_path: Ruta base para guardar el JSON (si se proporciona)

    Returns:
        Diccionario con la estructura:
        {
            "metadata": {...},
            "retroalimentacion": {
                "puntajes": [...],
                "comentario_narrativo": "",
                "resumen_para_moodle": ""
            }
        }

    Raises:
        RuntimeError: Si ANTHROPIC_API_KEY no está configurada
        FileNotFoundError: Si los archivos de rúbrica o prompt no existen
        ValueError: Si la respuesta no es JSON válido después de reintentos
    """
    # Importar aquí para evitar error si no está instalado
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError(
            "El paquete 'anthropic' no está instalado. "
            "Instálalo con: pip install anthropic"
        )

    # Verificar API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no está definido en las variables de entorno. "
            "Configúralo con: export ANTHROPIC_API_KEY='tu-api-key'"
        )

    logger.info(f"Generando retroalimentación con modelo: {model}")

    # Cargar archivos
    rubric = load_rubric(rubric_path)
    prompt_template = load_prompt_template(prompt_path)

    # Construir prompt
    full_prompt = build_prompt(
        prompt_template,
        rubric,
        student_text,
        activity_instructions,
        descripcion_yaml,
    )
    logger.debug(f"Prompt construido ({len(full_prompt)} caracteres)")

    # Crear cliente
    client = Anthropic(api_key=api_key)

    # Llamar al API
    logger.info("Enviando solicitud a Claude...")
    raw_text = _call_llm_for_feedback(client, full_prompt, model, max_tokens, temperature)
    logger.debug(f"Respuesta recibida ({len(raw_text)} caracteres)")

    # Parsear JSON con reintento
    llm_data = None
    parse_error = None

    try:
        llm_data = extract_json_from_response(raw_text)
        validate_feedback_structure(llm_data)
    except ValueError as exc:
        parse_error = str(exc)
        logger.warning(f"Error parseando respuesta inicial: {exc}. Reintentando con prompt de corrección...")

    # Reintento si falló el parseo
    if llm_data is None:
        fix_prompt = _build_json_fix_prompt(raw_text, parse_error or "Error desconocido")
        logger.info("Enviando solicitud de corrección de JSON...")

        try:
            fixed_text = _call_llm_for_feedback(client, fix_prompt, model, max_tokens, temperature)
            llm_data = extract_json_from_response(fixed_text)
            validate_feedback_structure(llm_data)
            logger.info("JSON corregido exitosamente en el reintento")
        except ValueError as exc:
            logger.error(f"Error en reintento de corrección de JSON: {exc}")
            raise ValueError(
                f"No se pudo obtener JSON válido después de reintento. "
                f"Error original: {parse_error}. Error en reintento: {exc}"
            )

    # Construir estructura final con metadata
    fecha_procesamiento = datetime.now(timezone.utc).isoformat()

    result = {
        "metadata": {
            "estudiante": estudiante,
            "archivo_original": archivo_original,
            "fecha_procesamiento": fecha_procesamiento,
            "curso": curso,
            "unidad": unidad,
            "actividad": actividad,
            "rubrica_usada": rubric_path.name,
            "descripcion_yaml": descripcion_yaml or "",
            "activity_instructions": activity_instructions or "",
            "student_text": student_text,
        },
        "retroalimentacion": {
            "puntajes": llm_data["puntajes"],
            "comentario_narrativo": llm_data["comentario_narrativo"],
            "resumen_para_moodle": llm_data["resumen_para_moodle"],
        },
    }

    # Validar estructura final antes de guardar
    _validate_final_structure(result)

    # Guardar si se especificó ruta
    if output_base_path is not None:
        output_path = _build_output_path(output_base_path, curso, unidad, actividad, archivo_original)
        _save_feedback_json(result, output_path)
        logger.info(f"Retroalimentación guardada en: {output_path}")

    logger.info("Retroalimentación generada exitosamente")
    return result


def _validate_final_structure(data: dict[str, Any]) -> None:
    """
    Valida la estructura final del JSON antes de guardar.

    Args:
        data: Diccionario con la estructura final

    Raises:
        ValueError: Si la estructura no es válida
    """
    # Validar presencia de claves top-level
    if "metadata" not in data or "retroalimentacion" not in data:
        raise ValueError("Estructura final debe contener 'metadata' y 'retroalimentacion'")

    # Validar metadata
    metadata_keys = [
        "estudiante", "archivo_original", "fecha_procesamiento", "curso",
        "unidad", "actividad", "rubrica_usada", "descripcion_yaml", "activity_instructions",
        "student_text"
    ]
    missing_metadata = [k for k in metadata_keys if k not in data["metadata"]]
    if missing_metadata:
        raise ValueError(f"Metadata falta claves: {missing_metadata}")

    # Validar tipos en metadata
    if not isinstance(data["metadata"]["estudiante"], str):
        raise ValueError("metadata.estudiante debe ser string")
    if not isinstance(data["metadata"]["archivo_original"], str):
        raise ValueError("metadata.archivo_original debe ser string")
    if not isinstance(data["metadata"]["fecha_procesamiento"], str):
        raise ValueError("metadata.fecha_procesamiento debe ser string")
    if not isinstance(data["metadata"]["curso"], str):
        raise ValueError("metadata.curso debe ser string")
    if not isinstance(data["metadata"]["unidad"], int):
        raise ValueError("metadata.unidad debe ser int")
    if not isinstance(data["metadata"]["actividad"], str):
        raise ValueError("metadata.actividad debe ser string")
    if not isinstance(data["metadata"]["rubrica_usada"], str):
        raise ValueError("metadata.rubrica_usada debe ser string")
    if not isinstance(data["metadata"]["descripcion_yaml"], str):
        raise ValueError("metadata.descripcion_yaml debe ser string")
    if not isinstance(data["metadata"]["activity_instructions"], str):
        raise ValueError("metadata.activity_instructions debe ser string")
    if not isinstance(data["metadata"]["student_text"], str):
        raise ValueError("metadata.student_text debe ser string")

    # Validar retroalimentacion (ya validada por validate_feedback_structure)
    retro_keys = ["puntajes", "comentario_narrativo", "resumen_para_moodle"]
    missing_retro = [k for k in retro_keys if k not in data["retroalimentacion"]]
    if missing_retro:
        raise ValueError(f"Retroalimentacion falta claves: {missing_retro}")


def _build_output_path(base_path: Path, curso: str, unidad: int, actividad: str, archivo_original: str) -> Path:
    """
    Construye la ruta de salida para el archivo JSON.

    Args:
        base_path: Ruta base (típicamente 'outputs')
        curso: Código del curso
        unidad: Número de unidad
        actividad: Identificador de actividad
        archivo_original: Nombre del archivo original (se usa el stem)

    Returns:
        Path completo: outputs/<course>/unidad_<n>/actividad_<id>/<original_stem>.json
    """
    # Sanitizar solo curso y actividad for directory names
    curso_safe = _sanitize_filename(curso)
    actividad_safe = _sanitize_filename(actividad)

    # Use original filename stem (without extension) for the JSON file
    original_stem = Path(archivo_original).stem

    return base_path / curso_safe / f"unidad_{unidad}" / f"actividad_{actividad_safe}" / f"{original_stem}.json"


def _sanitize_filename(name: str) -> str:
    """
    Sanitiza un string para uso seguro como nombre de archivo.

    Args:
        name: Nombre original

    Returns:
        Nombre sanitizado
    """
    # Reemplazar caracteres problemáticos
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Reemplazar espacios múltiples
    sanitized = re.sub(r'\s+', '_', sanitized)
    # Eliminar puntos al inicio/final
    sanitized = sanitized.strip('.')
    return sanitized or "unnamed"


def _save_feedback_json(data: dict[str, Any], output_path: Path) -> None:
    """
    Guarda el JSON de retroalimentación en el archivo especificado.

    Args:
        data: Diccionario con la retroalimentación
        output_path: Ruta donde guardar el archivo
    """
    # Crear directorios si no existen
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_cached_prompt_prefix(
    prompt_template: str,
    rubric: dict[str, Any],
    activity_instructions: str | None = None,
    descripcion_yaml: str | None = None,
    manual_criteria: list[str] | None = None,
) -> str:
    """
    Build the cacheable prefix of the prompt (everything except student text).

    This prefix remains constant across all students in a batch and can be cached.

    Args:
        prompt_template: Base prompt template
        rubric: Rubric dictionary
        activity_instructions: Activity instructions
        descripcion_yaml: YAML description
        manual_criteria: List of criteria names that will be scored manually (to exclude from AI)
    """
    # Filter out manual criteria from rubric for AI evaluation
    if manual_criteria:
        filtered_rubric = rubric.copy()
        filtered_rubric["criterios"] = [
            c for c in rubric.get("criterios", [])
            if c.get("nombre", "") not in manual_criteria
        ]
    else:
        filtered_rubric = rubric

    rubric_json = json.dumps(filtered_rubric, ensure_ascii=False, indent=2)

    parts = [prompt_template, ""]

    if activity_instructions:
        parts.append(f"Instrucciones de la actividad:\n\"\"\"\n{activity_instructions}\n\"\"\"\n")

    if descripcion_yaml:
        parts.append(f"Descripción de la actividad (YAML):\n\"\"\"\n{descripcion_yaml}\n\"\"\"\n")

    parts.append(f"Rúbrica (formato JSON):\n{rubric_json}\n")

    # Add strict output schema instructions
    parts.append("=" * 60)
    parts.append("FORMATO DE SALIDA OBLIGATORIO")
    parts.append("=" * 60)
    parts.append("""
IMPORTANTE: Debes producir ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta.
NO incluyas ningún campo adicional. NO incluyas total_score, grading_summary, detailed_rubric,
model_parameters, model_raw_response, token usage, ni ningún otro campo no especificado.

ESQUEMA DE SALIDA:
""")
    parts.append(OUTPUT_SCHEMA)
    parts.append("""
REGLAS:
1. El JSON debe ser válido y parseable directamente.
2. Cada criterio de la rúbrica debe tener una entrada en "puntajes".
3. "puntaje" debe ser un número (no string).
4. "maximo" debe ser el puntaje máximo posible para ese criterio según la rúbrica.
5. "justificacion" debe explicar específicamente por qué se asignó ese puntaje.
6. "comentario_narrativo" debe ser formativo, constructivo y personalizado.
7. "resumen_para_moodle" debe ser conciso (máximo 500 caracteres).
8. NO incluyas bloques de código markdown (```json) alrededor del JSON.
9. NO incluyas texto explicativo antes o después del JSON.

Devuelve SOLO el JSON, sin texto adicional antes o después.
""")

    return "\n".join(parts)


class DocumentTooLargeError(Exception):
    """Raised when a document exceeds the token limit."""
    pass


# Approximate token limit (leaving room for response)
MAX_INPUT_TOKENS = 180000
# Rough estimate: 1 token ≈ 4 characters for Spanish text
CHARS_PER_TOKEN = 4


def _estimate_tokens(char_count: int) -> int:
    """Estimate token count from character count."""
    return char_count // CHARS_PER_TOKEN


def _call_llm_with_caching(
    client: Any,
    cached_prefix: str,
    student_text: str,
    student_name: str,
    model: str,
    max_tokens: int,
    temperature: float,
    manual_scores: dict[str, Any] | None = None,
) -> str:
    """
    Call the Anthropic API with prompt caching enabled.

    The cached_prefix (instructions, rubric, output format) is marked for caching.
    Only the student_text and student_name change between calls.

    Args:
        client: Anthropic client
        cached_prefix: The constant part of the prompt (cacheable)
        student_text: The student's submission text (variable)
        student_name: Name of the student (from filename, used for addressing feedback)
        model: Model to use
        max_tokens: Maximum tokens
        temperature: Temperature for generation
        manual_scores: Pre-filled manual scores with comments to integrate into feedback

    Returns:
        Raw text response from the model

    Raises:
        DocumentTooLargeError: If the document exceeds token limits
    """
    # Check estimated token count before sending
    total_chars = len(cached_prefix) + len(student_text)
    estimated_tokens = _estimate_tokens(total_chars)

    if estimated_tokens > MAX_INPUT_TOKENS:
        raise DocumentTooLargeError(
            f"Documento demasiado grande ({estimated_tokens:,} tokens estimados, "
            f"límite: {MAX_INPUT_TOKENS:,}). Requiere revisión manual."
        )

    # Build per-student text with explicit name instruction
    student_section_parts = [
        f"NOMBRE DEL ESTUDIANTE: {student_name}",
        "(Usa este nombre al dirigirte al estudiante, NO uses nombres que aparezcan dentro del texto.)",
        "",
    ]

    # Add manual scores if provided
    if manual_scores:
        student_section_parts.append("EVALUACIÓN MANUAL DEL TUTOR (ya realizada, integrar en el comentario narrativo):")
        for criterio, data in manual_scores.items():
            score = data.get("puntaje", 0)
            maximo = data.get("maximo", 0)
            comment = data.get("comentario", "")
            student_section_parts.append(f"  - {criterio}: {score}/{maximo}")
            if comment:
                student_section_parts.append(f"    Observación del tutor: {comment}")
        student_section_parts.append("")
        student_section_parts.append("IMPORTANTE: Integra estas observaciones del tutor sobre formato/referencias en tu comentario narrativo de forma natural.")
        student_section_parts.append("")

    student_section_parts.append(f"Texto del estudiante:\n\"\"\"\n{student_text}\n\"\"\"")

    student_section = "\n".join(student_section_parts)

    # Build message with cache_control on the prefix
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": cached_prefix,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": student_section,
                    },
                ],
            }
        ],
    )

    content_blocks = response.content
    text_parts = []
    for block in content_blocks:
        if block.type == "text":
            text_parts.append(block.text)

    return "".join(text_parts).strip()


def generate_feedback_batch(
    submissions: list[dict[str, Any]],
    rubric_path: Path,
    prompt_path: Path,
    curso: str,
    unidad: int,
    actividad: str,
    activity_instructions: str | None = None,
    descripcion_yaml: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    output_base_path: Path | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    manual_criteria: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Genera retroalimentación para múltiples entregas con prompt caching.

    Uses Anthropic's prompt caching to reduce costs: the instructions, rubric,
    and output format are cached and reused across all students. Only the
    student text changes between API calls.

    Cost savings: ~90% reduction for cached tokens after first student.

    Args:
        submissions: Lista de diccionarios con:
            - id: ID de la entrega
            - text: Texto del estudiante
            - estudiante: Nombre del estudiante
            - archivo_original: Nombre del archivo original
            - manual_scores: (opcional) Dict con puntajes manuales pre-llenados
        rubric_path: Ruta al archivo de rúbrica
        prompt_path: Ruta al archivo de prompt
        curso: Código del curso
        unidad: Número de unidad
        actividad: Identificador de actividad
        activity_instructions: Instrucciones de la actividad
        descripcion_yaml: Descripción de la actividad desde YAML
        model: Modelo de Claude a usar
        output_base_path: Ruta base para guardar los JSON
        max_tokens: Maximum tokens for response
        temperature: Temperature for generation
        manual_criteria: List of criteria names scored manually (excluded from AI)

    Returns:
        Lista de diccionarios con resultados, cada uno con:
        - id: ID de la entrega
        - success: Si se generó exitosamente
        - feedback: Diccionario de retroalimentación (si success=True)
        - error: Mensaje de error (si success=False)
    """
    # Import here to avoid error if not installed
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError(
            "El paquete 'anthropic' no está instalado. "
            "Instálalo con: pip install anthropic"
        )

    # Verify API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no está definido en las variables de entorno. "
            "Configúralo con: export ANTHROPIC_API_KEY='tu-api-key'"
        )

    logger.info(f"Procesando lote de {len(submissions)} entregas con prompt caching")

    # Load rubric and prompt template once
    rubric = load_rubric(rubric_path)
    prompt_template = load_prompt_template(prompt_path)

    # Build the cacheable prefix (constant across all students)
    cached_prefix = _build_cached_prompt_prefix(
        prompt_template=prompt_template,
        rubric=rubric,
        activity_instructions=activity_instructions,
        descripcion_yaml=descripcion_yaml,
        manual_criteria=manual_criteria,
    )

    logger.debug(f"Cached prefix size: {len(cached_prefix)} characters")

    # Create client once
    client = Anthropic(api_key=api_key)

    results = []

    for i, submission in enumerate(submissions, 1):
        submission_id = submission.get("id", "unknown")
        student_text = submission.get("text", "")
        estudiante = submission.get("estudiante", str(submission_id))
        archivo_original = submission.get("archivo_original", "unknown")
        manual_scores = submission.get("manual_scores")  # Pre-filled manual scores

        logger.info(f"[{i}/{len(submissions)}] Procesando: {estudiante}")

        try:
            # Extract first name from estudiante for personalized feedback
            # Format varies:
            # - Moodle: "FIRSTNAME LASTNAME_ID_assignsubmission_file_..." -> first word of first part
            # - Manual: "Lastname_firstname_activity" -> second part (firstname)
            parts = estudiante.split("_")
            first_part = parts[0].strip()
            if " " in first_part:
                # Moodle format: "FIRSTNAME LASTNAME_..." -> extract first word
                student_name = first_part.split()[0].capitalize()
            elif len(parts) >= 2:
                # Manual format: "Lastname_firstname_..." -> second part is firstname
                student_name = parts[1].strip().capitalize()
            else:
                student_name = first_part.capitalize()

            # Call API with caching
            raw_text = _call_llm_with_caching(
                client=client,
                cached_prefix=cached_prefix,
                student_text=student_text,
                student_name=student_name,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                manual_scores=manual_scores,
            )

            # Parse JSON response
            llm_data = None
            parse_error = None

            try:
                llm_data = extract_json_from_response(raw_text)
                validate_feedback_structure(llm_data)
            except ValueError as exc:
                parse_error = str(exc)
                logger.warning(f"Error parseando respuesta: {exc}. Reintentando...")

            # Retry if parsing failed
            if llm_data is None:
                fix_prompt = _build_json_fix_prompt(raw_text, parse_error or "Error desconocido")
                fixed_text = _call_llm_for_feedback(client, fix_prompt, model, max_tokens, temperature)
                llm_data = extract_json_from_response(fixed_text)
                validate_feedback_structure(llm_data)

            # Build final structure
            from datetime import datetime, timezone
            fecha_procesamiento = datetime.now(timezone.utc).isoformat()

            feedback = {
                "metadata": {
                    "estudiante": estudiante,
                    "archivo_original": archivo_original,
                    "fecha_procesamiento": fecha_procesamiento,
                    "curso": curso,
                    "unidad": unidad,
                    "actividad": actividad,
                    "rubrica_usada": rubric_path.name,
                    "descripcion_yaml": descripcion_yaml or "",
                    "activity_instructions": activity_instructions or "",
                    "student_text": student_text,
                },
                "retroalimentacion": {
                    "puntajes": llm_data["puntajes"],
                    "comentario_narrativo": llm_data["comentario_narrativo"],
                    "resumen_para_moodle": llm_data["resumen_para_moodle"],
                },
            }

            # Save if output path specified
            if output_base_path is not None:
                output_path = _build_output_path(output_base_path, curso, unidad, actividad, archivo_original)
                _save_feedback_json(feedback, output_path)
                logger.info(f"Guardado: {output_path}")

            results.append({
                "id": submission_id,
                "success": True,
                "feedback": feedback,
            })

        except Exception as e:
            logger.error(f"Error procesando {estudiante}: {e}")
            results.append({
                "id": submission_id,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    logger.info(f"Lote completado: {successful}/{len(results)} exitosos")

    return results


def reprocess_feedback_from_directory(
    feedback_dir: Path,
    rubric_path: Path,
    prompt_path: Path,
    output_base_path: Path | None = None,
    original_files_dir: Path | None = None,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    recursive: bool = True,
) -> list[dict[str, Any]]:
    """
    Reprocess feedback for all JSON files in a directory.

    Reads existing feedback JSONs, extracts metadata and student_text,
    and regenerates feedback using the current prompt/rubric.

    Args:
        feedback_dir: Directory containing feedback JSON files
        rubric_path: Path to the rubric JSON file
        prompt_path: Path to the prompt template file
        output_base_path: Base path for output files (if None, overwrites originals)
        original_files_dir: Directory containing original student files (PDFs, etc.)
                           Used when student_text is missing from JSON
        model: Model to use for generation
        max_tokens: Maximum tokens for response
        temperature: Temperature for generation
        recursive: Whether to search subdirectories

    Returns:
        List of result dictionaries with:
        - file: Original JSON file path
        - success: Whether reprocessing succeeded
        - feedback: New feedback (if success)
        - error: Error message (if failed)
    """
    logger.info(f"Buscando archivos JSON en: {feedback_dir}")

    # Find all JSON files
    if recursive:
        json_files = list(feedback_dir.rglob("*.json"))
    else:
        json_files = list(feedback_dir.glob("*.json"))

    logger.info(f"Encontrados {len(json_files)} archivos JSON")

    results = []

    for json_file in json_files:
        logger.info(f"Procesando: {json_file}")

        try:
            result = _reprocess_single_feedback(
                json_file=json_file,
                rubric_path=rubric_path,
                prompt_path=prompt_path,
                output_base_path=output_base_path,
                original_files_dir=original_files_dir,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            results.append({
                "file": str(json_file),
                "success": True,
                "feedback": result,
            })
        except Exception as e:
            logger.error(f"Error procesando {json_file}: {e}")
            results.append({
                "file": str(json_file),
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    logger.info(f"Reprocesamiento completado: {successful}/{len(results)} exitosos")

    return results


def _reprocess_single_feedback(
    json_file: Path,
    rubric_path: Path,
    prompt_path: Path,
    output_base_path: Path | None,
    original_files_dir: Path | None,
    model: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    """
    Reprocess a single feedback JSON file.

    Args:
        json_file: Path to the feedback JSON
        rubric_path: Path to rubric
        prompt_path: Path to prompt template
        output_base_path: Base output path
        original_files_dir: Directory with original files
        model: Model to use
        max_tokens: Max tokens
        temperature: Temperature

    Returns:
        New feedback dictionary

    Raises:
        ValueError: If student_text cannot be obtained
        FileNotFoundError: If original file not found
    """
    # Load existing feedback JSON
    with json_file.open("r", encoding="utf-8") as f:
        existing = json.load(f)

    # Extract metadata
    metadata = existing.get("metadata", {})

    estudiante = metadata.get("estudiante", "")
    archivo_original = metadata.get("archivo_original", "")
    curso = metadata.get("curso", "")
    unidad = metadata.get("unidad", 1)
    actividad = metadata.get("actividad", "")
    descripcion_yaml = metadata.get("descripcion_yaml", "")
    activity_instructions = metadata.get("activity_instructions", "")

    # Get student_text - either from JSON or from original file
    student_text = metadata.get("student_text", "")

    if not student_text:
        # Need to extract from original file
        if not original_files_dir:
            raise ValueError(
                f"El JSON {json_file} no contiene 'student_text' y no se proporcionó "
                f"'original_files_dir' para extraer el texto del archivo original."
            )

        student_text = _extract_text_from_original(
            original_files_dir, archivo_original
        )

    if not student_text:
        raise ValueError(f"No se pudo obtener student_text para {json_file}")

    # Validate required fields
    if not estudiante:
        # Try to get from filename
        estudiante = json_file.stem

    if not curso:
        raise ValueError(f"Campo 'curso' faltante en metadata de {json_file}")

    if not isinstance(unidad, int):
        unidad = int(unidad) if unidad else 1

    if not actividad:
        raise ValueError(f"Campo 'actividad' faltante en metadata de {json_file}")

    # Generate new feedback
    return generate_feedback_for_text(
        student_text=student_text,
        rubric_path=rubric_path,
        prompt_path=prompt_path,
        estudiante=estudiante,
        archivo_original=archivo_original,
        curso=curso,
        unidad=unidad,
        actividad=actividad,
        activity_instructions=activity_instructions or None,
        descripcion_yaml=descripcion_yaml or None,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        output_base_path=output_base_path,
    )


def _extract_text_from_original(original_files_dir: Path, archivo_original: str) -> str:
    """
    Extract text from an original student file.

    Searches for the file in the directory and extracts text using
    the appropriate parser.

    Args:
        original_files_dir: Directory containing original files
        archivo_original: Original filename

    Returns:
        Extracted text

    Raises:
        FileNotFoundError: If file not found
        ValueError: If text extraction fails
    """
    # Import here to avoid circular imports
    from ..processing.parser import extract_text

    # Search for the file
    possible_paths = [
        original_files_dir / archivo_original,
        *original_files_dir.rglob(archivo_original),
    ]

    file_path = None
    for path in possible_paths:
        if path.exists() and path.is_file():
            file_path = path
            break

    if not file_path:
        raise FileNotFoundError(
            f"Archivo original no encontrado: {archivo_original} "
            f"en {original_files_dir}"
        )

    logger.info(f"Extrayendo texto de: {file_path}")

    try:
        result = extract_text(file_path)
        return result.text
    except Exception as e:
        raise ValueError(f"Error extrayendo texto de {file_path}: {e}") from e


def load_feedback_json(json_path: Path) -> dict[str, Any]:
    """
    Load a feedback JSON file and return its contents.

    Args:
        json_path: Path to the feedback JSON file

    Returns:
        Dictionary with feedback data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If JSON is invalid
    """
    logger.debug(f"Cargando feedback desde: {json_path}")
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)
