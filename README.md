# Coach Ciclismo — Telegram Bot

## Setup en 4 pasos

---

### Paso 1 — Crear el bot en Telegram (5 min)

1. Abrí Telegram y buscá @BotFather
2. Mandá /newbot
3. Elegí un nombre: ej. "Coach Ciclismo Federico"
4. Elegí un username: ej. "coach_ciclismo_federico_bot"
5. BotFather te da un TOKEN — guardalo (formato: 123456789:ABCdef...)

---

### Paso 2 — Obtener API Key de Anthropic

1. Entrá a https://console.anthropic.com
2. API Keys → Create Key
3. Guardala (formato: sk-ant-api03-...)

---

### Paso 3 — Deploy en Railway (gratis, 5 min)

1. Creá cuenta en https://railway.app (con GitHub)
2. New Project → Deploy from GitHub repo
   - (Antes subí los archivos a un repo GitHub privado)
3. En Variables de entorno agregá:
   - ANTHROPIC_API_KEY = tu key
   - TELEGRAM_TOKEN = tu token de BotFather
4. Railway detecta requirements.txt y deploya solo
5. En Settings → Start Command: python bot.py

**Alternativa sin GitHub:** Railway también permite subir archivos directamente.

---

### Paso 4 — Probar

1. Buscá tu bot en Telegram por el username que elegiste
2. Mandá /start
3. Listo

---

## Comandos disponibles

| Comando | Función |
|---------|---------|
| /start | Iniciar / ver plan activo |
| /sesion | Sesión del día con bloques completos |
| /checkin | Reporte semanal + ajuste de plan |
| /alerta | Señales de fatiga a monitorear |
| /reset | Reiniciar conversación |
| Texto libre | Cualquier consulta |

---

## Costo operativo estimado

- Railway: gratis (plan hobby, 500hs/mes)
- Anthropic API: ~$0.01-0.03 por consulta con claude-sonnet
- Uso diario normal (5-10 consultas/día): < $5/mes

---

## Actualizar el plan

Cuando cambies de semana o el coach ajuste el plan,
editá la variable SYSTEM_PROMPT en bot.py y redeploya
(en Railway es un push a GitHub o subir el archivo nuevo).
