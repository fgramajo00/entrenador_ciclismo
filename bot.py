import os
import asyncio
import json
import tempfile
import requests
from datetime import date, datetime, timedelta
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
INTERVALS_ATHLETE_ID = os.environ.get("INTERVALS_ATHLETE_ID")
INTERVALS_API_KEY = os.environ.get("INTERVALS_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN no definido")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY no definido")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"

INTERVALS_BASE = "https://intervals.icu/api/v1"

# ── Intervals.icu ──

def intervals_get(endpoint):
    if not INTERVALS_ATHLETE_ID or not INTERVALS_API_KEY:
        return None
    try:
        url = f"{INTERVALS_BASE}/athlete/{INTERVALS_ATHLETE_ID}{endpoint}"
        r = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None

def get_athlete_profile():
    return intervals_get("")

def get_recent_activities(days=7):
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()
    return intervals_get(f"/activities?oldest={oldest}&newest={newest}")

def get_wellness(days=7):
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()
    return intervals_get(f"/wellness?oldest={oldest}&newest={newest}")

def get_todays_wellness():
    today = date.today().isoformat()
    data = intervals_get(f"/wellness?oldest={today}&newest={today}")
    if data and len(data) > 0:
        return data[0]
    return None

def build_data_context():
    sections = []
    profile = get_athlete_profile()
    if profile:
        ftp = profile.get("ftp", "?")
        weight = profile.get("weight", "?")
        max_hr = profile.get("max_hr", "?")
        rest_hr = profile.get("resting_hr", "?")
        ctl = profile.get("ctl", "?")
        atl = profile.get("atl", "?")
        tsb = profile.get("tsb", "?")
        sections.append(
            f"DATOS INTERVALS.ICU EN VIVO:\n"
            f"- FTP actual: {ftp}W\n"
            f"- Peso: {weight} kg\n"
            f"- W/kg: {round(ftp/weight, 2) if isinstance(ftp,(int,float)) and isinstance(weight,(int,float)) and weight > 0 else '?'}\n"
            f"- FC max: {max_hr} bpm\n"
            f"- FC reposo: {rest_hr} bpm\n"
            f"- CTL (fitness): {ctl}\n"
            f"- ATL (fatiga): {atl}\n"
            f"- TSB (forma): {tsb}"
        )
    wellness = get_todays_wellness()
    if wellness:
        w_parts = []
        if wellness.get("weight"): w_parts.append(f"Peso hoy: {wellness['weight']} kg")
        if wellness.get("restingHR"): w_parts.append(f"FC reposo hoy: {wellness['restingHR']} bpm")
        if wellness.get("hrv"): w_parts.append(f"HRV: {wellness['hrv']}")
        if wellness.get("sleepQuality"): w_parts.append(f"Calidad sueño: {wellness['sleepQuality']}")
        if wellness.get("fatigue"): w_parts.append(f"Fatiga percibida: {wellness['fatigue']}")
        if wellness.get("mood"): w_parts.append(f"Estado ánimo: {wellness['mood']}")
        if wellness.get("motivation"): w_parts.append(f"Motivación: {wellness['motivation']}")
        if w_parts:
            sections.append("WELLNESS HOY:\n" + "\n".join(f"- {p}" for p in w_parts))
    activities = get_recent_activities(7)
    if activities:
        rides = [a for a in activities if a.get("type") in ("Ride", "VirtualRide", None)]
        if rides:
            act_lines = []
            weekly_tss = 0
            for a in rides[-7:]:
                a_date = a.get("start_date_local", "")[:10]
                a_name = a.get("name", "Sin nombre")
                a_tss = a.get("icu_training_load", 0) or 0
                a_if = a.get("icu_intensity", 0) or 0
                a_dur = round((a.get("moving_time", 0) or 0) / 60)
                a_np = a.get("icu_weighted_avg_watts", 0) or 0
                a_avg = a.get("icu_average_watts", 0) or 0
                a_hr = a.get("icu_average_hr", 0) or 0
                weekly_tss += a_tss
                act_lines.append(
                    f"  {a_date} | {a_name} | {a_dur}min | "
                    f"TSS:{round(a_tss)} IF:{round(a_if,2)} NP:{round(a_np)}W "
                    f"Avg:{round(a_avg)}W HR:{round(a_hr)}bpm"
                )
            sections.append(
                f"ACTIVIDADES ÚLTIMOS 7 DÍAS (TSS semanal: {round(weekly_tss)}):\n" +
                "\n".join(act_lines)
            )
    if not sections:
        return "\n[Intervals.icu no disponible - decidir con datos del plan]\n"
    return "\n\n".join(sections)

# ── ZWO Generation ──

ZWO_PROMPT = """Generá la sesión de hoy como un JSON para archivo ZWO de Zwift.
Basate en los datos reales de Intervals.icu. Respondé SOLO con el JSON, sin texto adicional, sin backticks.

Formato requerido:
{
  "name": "nombre de la sesion",
  "description": "objetivo fisiologico breve",
  "segments": [
    {"type": "warmup", "duration": 600, "power_low": 0.40, "power_high": 0.65, "cadence": 85},
    {"type": "steady", "duration": 1200, "power": 0.65, "cadence": 90},
    {"type": "intervals", "repeat": 3, "on_duration": 300, "off_duration": 120, "on_power": 0.88, "off_power": 0.55, "cadence": 95, "cadence_rest": 80},
    {"type": "steady", "duration": 300, "power": 0.55, "cadence": 85},
    {"type": "cooldown", "duration": 600, "power_low": 0.55, "power_high": 0.40, "cadence": 80}
  ]
}

REGLAS:
- power es fracción del FTP (0.65 = 65% FTP). Zwift ajusta automáticamente a los watts del rider.
- type puede ser: warmup, steady, intervals, freeride, cooldown
- duration en segundos
- Máximo 75 min total (90 sábados). Variabilidad cada 5-15 min para tolerar rodillo.
- Aplicar metodología Coggan según fase de entrenamiento actual
- Si TSB < -20: sesión de recuperación
- Si no hay actividad hace >2 días: reactivación suave"""

def json_to_zwo(workout_json):
    name = workout_json.get("name", "Sesion Coach IA")
    desc = workout_json.get("description", "")
    segments = workout_json.get("segments", [])

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<workout_file>',
        f'    <author>Coach Ciclismo IA</author>',
        f'    <name>{name}</name>',
        f'    <description>{desc}</description>',
        '    <sportType>bike</sportType>',
        '    <tags/>',
        '    <workout>'
    ]

    for seg in segments:
        t = seg.get("type", "steady")
        cad = f' Cadence="{seg["cadence"]}"' if seg.get("cadence") else ""

        if t == "warmup":
            xml_parts.append(
                f'        <Warmup Duration="{seg["duration"]}" '
                f'PowerLow="{seg.get("power_low", 0.40)}" '
                f'PowerHigh="{seg.get("power_high", 0.65)}"{cad}/>'
            )
        elif t == "cooldown":
            xml_parts.append(
                f'        <Cooldown Duration="{seg["duration"]}" '
                f'PowerLow="{seg.get("power_low", 0.55)}" '
                f'PowerHigh="{seg.get("power_high", 0.40)}"{cad}/>'
            )
        elif t == "steady":
            xml_parts.append(
                f'        <SteadyState Duration="{seg["duration"]}" '
                f'Power="{seg.get("power", 0.65)}"{cad}/>'
            )
        elif t == "intervals":
            cad_rest = f' CadenceResting="{seg["cadence_rest"]}"' if seg.get("cadence_rest") else ""
            xml_parts.append(
                f'        <IntervalsT Repeat="{seg.get("repeat", 3)}" '
                f'OnDuration="{seg.get("on_duration", 300)}" '
                f'OffDuration="{seg.get("off_duration", 120)}" '
                f'OnPower="{seg.get("on_power", 0.88)}" '
                f'OffPower="{seg.get("off_power", 0.55)}"{cad}{cad_rest}/>'
            )
        elif t == "freeride":
            xml_parts.append(
                f'        <FreeRide Duration="{seg["duration"]}" FlatRoad="0"/>'
            )

    xml_parts.extend([
        '    </workout>',
        '</workout_file>'
    ])

    return "\n".join(xml_parts)

# ── System Prompt ──

SYSTEM_PROMPT = """Actúas como entrenador de ciclismo profesional de alto rendimiento de Federico. Responde siempre en español. Sé técnico, directo y crítico. Sin frases motivacionales vacías.

IMPORTANTE: Antes de cada respuesta sobre entrenamiento se te inyectarán datos reales de Intervals.icu (CTL, ATL, TSB, últimas actividades, wellness). USÁ ESOS DATOS para tomar decisiones. No le pidas datos que ya tenés. Solo preguntale cosas subjetivas que no estén en los datos.

PERFIL DE FEDERICO:
- Hombre amateur
- FTP histórico pre-inactividad: 256W
- 60 días sin entrenar antes de retomar (26 mayo 2026)
- Sin estatinas, sin lesiones activas
- 100% indoor, potenciómetro + pulsómetro
- Plataformas: Zwift y MyWhoosh
- Sesiones máximo 60-75 min (90 sábado). Rodillo es duro para la cabeza.
- Objetivo corto plazo: Transmontaña MTB 15 agosto 2026, ~67kg y ~3.8-4.0 w/kg
- Objetivo largo plazo: próximo año 5 w/kg

METODOLOGÍA:
- Zonas Coggan basadas en FTP real de Intervals.icu
- Periodización por TSS/IF/CTL/ATL/TSB
- Déficit calórico 300-400 kcal/día máximo, proteína 2.0-2.2 g/kg
- Priorizar consistencia, nunca carga extrema
- Recomendar ERG mode para sesiones estructuradas, SIM mode para Z2 largo
- Cada sesión tiene que tener variabilidad (cambios cada 5-15 min) para tolerar rodillo

LÓGICA DE DECISIÓN AUTOMÁTICA:
- Si TSB < -20: reducir carga, priorizar recuperación
- Si TSB > 15: puede tolerar más carga
- Si TSB entre -10 y 5: rango óptimo para entrenar
- Si FC reposo subió >5bpm sobre línea base: día de recuperación o descanso
- Si última actividad fue ayer con TSS > 80: hoy recuperación activa o descanso
- Si no hay actividad hace >2 días: reactivar suave
- Ajustar zonas automáticamente si FTP de Intervals.icu cambió

FORMATO DE RESPUESTA PARA SESIONES:
1. Justificación basada en datos reales (CTL/ATL/TSB, última actividad)
2. Protocolo estructurado (calentamiento, bloques con tiempo/zona/%FTP/watts/FC/cadencia/RPE, enfriamiento)
3. Métricas esperadas (TSS, IF, Kcal)
4. Señales de alerta (cuándo cortar)
5. Nutrición del día

REGLAS CRÍTICAS:
- NUNCA pedir datos que ya están en el contexto de Intervals.icu
- Ser crítico si Federico quiere saltear descansos
- Si los datos muestran sobreentrenamiento, negarse a dar sesión intensa"""

# ── Bot Logic ──

conversations = {}

def get_history(user_id: int) -> list:
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]

def trim_history(history: list, max_messages: int = 20) -> list:
    if len(history) > max_messages:
        return history[-max_messages:]
    return history

async def call_claude(history, extra_context="", max_tokens=1500):
    system = SYSTEM_PROMPT
    if extra_context:
        system = f"{SYSTEM_PROMPT}\n\n{extra_context}"
    response = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=trim_history(history)
        )
    )
    return response.content[0].text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    intervals_status = "desconectado"
    if INTERVALS_ATHLETE_ID and INTERVALS_API_KEY:
        profile = get_athlete_profile()
        if profile:
            ftp = profile.get("ftp", "?")
            weight = profile.get("weight", "?")
            ctl = profile.get("ctl", "?")
            intervals_status = f"conectado (FTP: {ftp}W | Peso: {weight}kg | CTL: {ctl})"
    await update.message.reply_text(
        f"Coach activo.\n\n"
        f"Intervals.icu: {intervals_status}\n"
        f"Objetivo: Transmontaña 15/08\n\n"
        f"/sesion — sesión del día + archivo ZWO\n"
        f"/zwo — solo el archivo ZWO de hoy\n"
        f"/estado — tu CTL/ATL/TSB + últimas actividades\n"
        f"/checkin — análisis semanal automático\n"
        f"/alerta — señales de fatiga\n"
        f"/reset — reiniciar conversación\n\n"
        f"O escribime directamente cualquier consulta."
    )

async def cmd_sesion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    data_context = build_data_context()
    today = date.today().strftime("%A %d/%m/%Y")
    prompt = f"Hoy es {today}. Basándote en mis datos reales de Intervals.icu, dame la sesión de hoy."
    history.append({"role": "user", "content": prompt})
    try:
        reply = await call_claude(history, data_context)
        history.append({"role": "assistant", "content": reply})
        conversations[user_id] = trim_history(history)
        for chunk in split_message(reply):
            await update.message.reply_text(chunk)
        # Auto-generate ZWO
        await send_zwo(update, context, data_context, today)
    except Exception as e:
        history.pop()
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

async def send_zwo(update, context, data_context, today):
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
        zwo_history = [{"role": "user", "content": f"Hoy es {today}. {ZWO_PROMPT}"}]
        zwo_json_str = await call_claude(zwo_history, data_context, max_tokens=1000)
        
        # Clean response
        zwo_json_str = zwo_json_str.strip()
        if zwo_json_str.startswith("```"):
            zwo_json_str = zwo_json_str.split("\n", 1)[1] if "\n" in zwo_json_str else zwo_json_str[3:]
        if zwo_json_str.endswith("```"):
            zwo_json_str = zwo_json_str[:-3]
        zwo_json_str = zwo_json_str.strip()
        
        workout = json.loads(zwo_json_str)
        zwo_xml = json_to_zwo(workout)
        
        filename = f"coach_{date.today().isoformat()}.zwo"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zwo', delete=False, encoding='utf-8') as f:
            f.write(zwo_xml)
            tmp_path = f.name
        
        with open(tmp_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption="Archivo ZWO listo. Copialo a Documents/Zwift/Workouts/TU_ZWIFT_ID/"
            )
        os.unlink(tmp_path)
    except Exception as e:
        await update.message.reply_text(f"No pude generar el ZWO: {type(e).__name__}: {e}")

async def cmd_zwo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    data_context = build_data_context()
    today = date.today().strftime("%A %d/%m/%Y")
    await send_zwo(update, context, data_context, today)

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    data = build_data_context()
    if "no disponible" in data:
        await update.message.reply_text("No pude conectar con Intervals.icu. Verificá las credenciales.")
        return
    await update.message.reply_text(data)

async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    data_context = build_data_context()
    prompt = (
        "Hacé el análisis semanal completo basándote en los datos reales de Intervals.icu. "
        "Evaluá: progresión de CTL, carga acumulada, calidad de sesiones, "
        "tendencia de peso, y decidí si hay que ajustar el plan para la próxima semana."
    )
    history.append({"role": "user", "content": prompt})
    try:
        reply = await call_claude(history, data_context)
        history.append({"role": "assistant", "content": reply})
        conversations[user_id] = trim_history(history)
        for chunk in split_message(reply):
            await update.message.reply_text(chunk)
    except Exception as e:
        history.pop()
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

async def cmd_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    data_context = build_data_context()
    prompt = "Analizá mis datos actuales y decime si hay alguna señal de alerta o sobreentrenamiento."
    history.append({"role": "user", "content": prompt})
    try:
        reply = await call_claude(history, data_context)
        history.append({"role": "assistant", "content": reply})
        conversations[user_id] = trim_history(history)
        for chunk in split_message(reply):
            await update.message.reply_text(chunk)
    except Exception as e:
        history.pop()
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text("Conversación reiniciada.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    history = get_history(user_id)
    history.append({"role": "user", "content": user_text})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    data_context = build_data_context()
    try:
        reply = await call_claude(history, data_context)
        history.append({"role": "assistant", "content": reply})
        conversations[user_id] = trim_history(history)
        for chunk in split_message(reply):
            await update.message.reply_text(chunk)
    except Exception as e:
        history.pop()
        await update.message.reply_text(f"Error: {type(e).__name__}: {e}")

def split_message(text: str, max_length: int = 4000) -> list:
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip('\n')
    return chunks

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sesion", cmd_sesion))
    app.add_handler(CommandHandler("zwo", cmd_zwo))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("alerta", cmd_alerta))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()
