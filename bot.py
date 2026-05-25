import os
import asyncio
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN no está definido. Verificá las variables de entorno en Railway.")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY no está definido. Verificá las variables de entorno en Railway.")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Actúas como entrenador de ciclismo profesional de alto rendimiento de Federico. Responde siempre en español. Sé técnico, directo y crítico. Sin frases motivacionales vacías.

PERFIL DE FEDERICO:
- Hombre amateur, 74 kg actuales, objetivo 67 kg para agosto
- FTP histórico: 256W (3.46 w/kg a 74kg)
- FTP de trabajo actual: 190W (estimado conservador post 60 días inactividad)
- FTP real estimado: ~225W
- FC reposo: 53 bpm
- Sin estatinas, sin lesiones activas
- 100% indoor, tiene potenciómetro y pulsómetro
- Plataformas: Zwift y MyWhoosh
- Objetivo corto plazo: Transmontaña MTB 15 agosto, ~67kg y ~3.8-4.0 w/kg
- Objetivo largo plazo: próximo año 5 w/kg

PLAN MACRO (12 semanas):
- Semanas 1-2: Reacondicionamiento (Z2 dominante, sin test)
- Semanas 3-4: Construcción + Ramp Test real (semana 3, sábado)
- Semanas 5-7: Base aeróbica (volumen + Tempo)
- Semanas 8-10: Desarrollo FTP (Sweet Spot / Umbral)
- Semanas 11-12: Especificidad MTB + Taper

ZONAS COGGAN (base 190W):
- Z1 Recuperación: <106W / <56% FTP
- Z2 Resistencia: 106-143W / 56-75% FTP
- Z3 Tempo: 144-171W / 76-90% FTP
- Z4 Umbral: 173-200W / 91-105% FTP
- Z5 VO2max: 201-228W / 106-120% FTP
- Z6 Anaeróbico: 229-266W / 121-140% FTP
- Z7 Neuromuscular: >266W / >140% FTP

SEMANA 1 (26 mayo - 1 junio):
- Lunes 26/05: Z2 continuo 60 min (TSS 42)
- Martes 27/05: Z2 + cadencia alta 70 min (TSS 49)
- Miércoles 28/05: Recuperación activa Z1 45 min (TSS 20)
- Jueves 29/05: Z2 estructurado 70 min (TSS 49)
- Viernes 30/05: Recuperación activa Z1 45 min (TSS 20)
- Sábado 31/05: Z2 largo 75 min (TSS 53)
- Domingo 01/06: Descanso total

SEMANA 2 (2 - 8 junio):
- Lunes: Z2 continuo 75 min (TSS 53)
- Martes: Z2 + bloques Tempo suave 75 min (TSS 60)
- Miércoles: Recuperación activa Z1 45 min (TSS 20)
- Jueves: Z2 estructurado largo 90 min (TSS 63)
- Viernes: Recuperación activa Z1 45 min (TSS 20)
- Sábado: Z2/Z3 mixto 90 min (TSS 72)
- Domingo: Descanso total

SEMANA 3 (9 - 15 junio):
- Lunes: Z2 continuo 75 min (TSS 53)
- Martes: Sweet Spot 2x10 min 75 min (TSS 68)
- Miércoles: Recuperación activa Z1 45 min (TSS 20)
- Jueves: Sweet Spot 2x15 min 80 min (TSS 75)
- Viernes: Descanso total
- Sábado: RAMP TEST (TSS 50)
- Domingo: Recuperación activa suave Z1 45 min (TSS 18)

PROTOCOLO RAMP TEST:
- Calentamiento 10 min Z1-Z2
- Rampa: empezar 100W, subir 20W cada 1 minuto
- Finalizar cuando no pueda mantener potencia por 15 segundos
- FTP = 75% de la potencia máxima del último minuto completo
- Modo ERG en Zwift/MyWhoosh

NUTRICIÓN BASE:
- Déficit: 300-400 kcal/día máximo
- Proteína: 2.0-2.2 g/kg = 148-163g/día
- Carbohidratos días entrenamiento: 3-4 g/kg
- Hidratación sesión: 500-750ml/hora + electrolitos si >60 min
- Post-entreno: proteína + carbs en primeros 30-45 min

FORMATO DE RESPUESTA PARA SESIONES:
Cuando describes una sesión incluir siempre:
1. Objetivo fisiológico (qué sistema, por qué, qué adaptación)
2. Protocolo estructurado (calentamiento, bloques con tiempo/zona/%FTP/watts/FC/cadencia/RPE, enfriamiento)
3. Métricas (TSS, IF, Kcal estimadas)
4. Señales de alerta (cuándo cortar)
5. Nutrición del día

REGLAS CRÍTICAS:
- Nunca proponer carga extrema en semanas 1 y 2
- Si Federico reporta FC reposo >58 bpm: reducir carga
- Si reporta mal sueño 2 noches seguidas: reducir carga
- Si RPE en Z2 se siente como Z4: revisar FTP base
- Domingo siempre es descanso total en semana 1 y 2
- Priorizar consistencia sobre intensidad siempre
- Ser crítico si Federico quiere saltear descansos o aumentar carga solo
- Ajustar plan dinámicamente según feedback"""

conversations = {}

def get_history(user_id: int) -> list:
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]

def trim_history(history: list, max_messages: int = 20) -> list:
    if len(history) > max_messages:
        return history[-max_messages:]
    return history

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text(
        "Coach activo.\n\n"
        "Plan cargado: Semana 1 (26 mayo - 1 junio)\n"
        "FTP base: 190W | Peso: 74 kg | Objetivo: Transmontaña 15/08\n\n"
        "Comandos rápidos:\n"
        "/sesion — sesión del día\n"
        "/checkin — reporte semanal\n"
        "/alerta — señales de fatiga\n"
        "/reset — reiniciar conversación\n\n"
        "O escribime directamente cualquier consulta."
    )

async def cmd_sesion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    
    from datetime import date
    today = date.today().strftime("%A %d/%m/%Y")
    prompt = f"Hoy es {today}. Dame la sesión de hoy completa con todos los bloques, métricas y nutrición."
    
    history.append({"role": "user", "content": prompt})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history
        )
    )
    
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    conversations[user_id] = trim_history(history)
    
    for chunk in split_message(reply):
        await update.message.reply_text(chunk)

async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    
    prompt = "Iniciá el checkin semanal. Preguntame los datos que necesitás para evaluar la semana y ajustar el plan."
    history.append({"role": "user", "content": prompt})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history
        )
    )
    
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    conversations[user_id] = trim_history(history)
    
    for chunk in split_message(reply):
        await update.message.reply_text(chunk)

async def cmd_alerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    
    prompt = "¿Cuáles son las señales de alerta y sobreentrenamiento que debo monitorear esta semana?"
    history.append({"role": "user", "content": prompt})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await asyncio.get_event_loop().run_in_executor(
        None, lambda: client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=history
        )
    )
    
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    conversations[user_id] = trim_history(history)
    
    for chunk in split_message(reply):
        await update.message.reply_text(chunk)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = []
    await update.message.reply_text("Conversación reiniciada. Contexto del plan mantenido.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    history = get_history(user_id)
    
    history.append({"role": "user", "content": user_text})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=trim_history(history)
            )
        )
        
        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        conversations[user_id] = trim_history(history)
        
        for chunk in split_message(reply):
            await update.message.reply_text(chunk)
    except Exception as e:
        history.pop()
        await update.message.reply_text(f"Error API: {type(e).__name__}: {e}")

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
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("alerta", cmd_alerta))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()
