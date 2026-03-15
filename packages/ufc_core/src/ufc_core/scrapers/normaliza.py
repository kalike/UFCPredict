import json
import re
from datetime import datetime
from pathlib import Path


def limpiar_nombre_oponente(opponent_text):
    """
    Extrae y limpia el nombre del oponente del texto.
    Elimina saltos de línea y espacios extra.
    """
    if not opponent_text:
        return ""

    # Eliminar saltos de línea y espacios múltiples
    texto_limpio = re.sub(r"\s+", " ", opponent_text)

    # Buscar el patrón: nombre_luchador vs nombre_oponente
    # El nombre del oponente suele estar después del nombre del luchador
    partes = texto_limpio.strip().split()

    # Filtrar palabras vacías y obtener los últimos 2-3 términos (nombre y apellido del oponente)
    palabras_validas = [p for p in partes if p and len(p) > 1]

    # Típicamente el oponente está en las últimas posiciones
    if len(palabras_validas) >= 2:
        # Tomar los últimos 2 elementos como nombre completo
        nombre_oponente = " ".join(palabras_validas[-2:])
        return nombre_oponente

    return texto_limpio.strip() if texto_limpio else ""


def limpiar_evento(event_text):
    """
    Extrae y limpia el nombre del evento.
    Elimina fechas y espacios extra.
    """
    if not event_text:
        return ""

    # Eliminar saltos de línea y espacios múltiples
    texto_limpio = re.sub(r"\s+", " ", event_text)

    # Eliminar fechas (patrón: Mes. DD, YYYY)
    texto_limpio = re.sub(r"\w+\.\s+\d{1,2},\s+\d{4}", "", texto_limpio)

    # Limpiar espacios extra y retornar
    return texto_limpio.strip()


def filtrar_peleadores_con_peleas(fighters_data):
    """
    Filtra los peleadores que tienen al menos una pelea.
    """
    fighters_con_peleas = []
    fighters_sin_peleas = []

    for fighter in fighters_data:
        # Verificar si tiene peleas y si la lista no está vacía
        if (
            "fights" in fighter
            and isinstance(fighter["fights"], list)
            and len(fighter["fights"]) > 0
        ):
            fighters_con_peleas.append(fighter)
        else:
            fighters_sin_peleas.append(fighter)

    print("\n📊 Estadísticas de filtrado:")
    print(f"   - Peleadores con peleas: {len(fighters_con_peleas)}")
    print(f"   - Peleadores sin peleas (excluidos): {len(fighters_sin_peleas)}")

    # Mostrar algunos ejemplos de peleadores sin peleas
    if fighters_sin_peleas:
        print("\n🚫 Ejemplos de peleadores excluidos (sin peleas):")
        for fighter in fighters_sin_peleas[:5]:  # Mostrar los primeros 5
            print(f"   - {fighter.get('name', 'Sin nombre')}")

    return fighters_con_peleas


def normalizar_fighters_data(input_file, output_file):
    """
    Normaliza los datos de fighters del archivo JSON y filtra los que tienen peleas.
    """
    try:
        # Leer el archivo JSON
        with open(input_file, encoding="utf-8") as f:
            content = f.read()

            # Intentar cargar el JSON
            try:
                fighters_data = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"❌ Error al decodificar JSON: {e}")
                print("Verificando el contenido del archivo...")

                # Mostrar las primeras líneas para depuración
                lines = content.split("\n")[:10]
                for i, line in enumerate(lines, 1):
                    print(f"Línea {i}: {line}")

                return

        print("\n🔄 Normalizando datos...")

        # Normalizar los datos
        total_fights = 0
        for fighter in fighters_data:
            if "fights" in fighter and isinstance(fighter["fights"], list):
                for fight in fighter["fights"]:
                    # Normalizar opponent
                    if "opponent" in fight:
                        fight["opponent"] = limpiar_nombre_oponente(fight["opponent"])

                    # Normalizar event
                    if "event" in fight:
                        fight["event"] = limpiar_evento(fight["event"])

                    total_fights += 1

        print("✅ Normalización completada")
        print(f"   - Total de peleas normalizadas: {total_fights}")

        # Filtrar peleadores con al menos una pelea
        print("\n🔍 Filtrando peleadores con peleas...")
        fighters_con_peleas = filtrar_peleadores_con_peleas(fighters_data)

        # Guardar el archivo normalizado solo con peleadores que tienen peleas
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(fighters_con_peleas, f, ensure_ascii=False, indent=4)

        print(f"\n✅ Datos normalizados y filtrados guardados en: {output_file}")
        print("📊 Resumen final:")
        print(f"   - Total de luchadores originales: {len(fighters_data)}")
        print(f"   - Total de luchadores con peleas guardados: {len(fighters_con_peleas)}")
        print(f"   - Total de peleas normalizadas: {total_fights}")

    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {input_file}")
        print("Asegúrate de que el archivo existe en la ruta especificada")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")


if __name__ == "__main__":
    # Definir archivos de entrada y salida
    input_file = "data/fighters_all.json"
    # Obtener la fecha de creación del archivo de entrada
    creation_date = datetime.fromtimestamp(Path(input_file).stat().st_ctime).strftime("%Y-%m-%d")

    # Generar el nombre del archivo de salida con la fecha de creación
    output_file = "data/fighters_all_normal.json"

    # Normalizar datos
    normalizar_fighters_data(input_file, output_file)
