# Backend — Voice Agent with Murf Falcon TTS

The Python backend for the Voice Agent Starter. It runs a real-time voice AI pipeline using [LiveKit Agents](https://docs.livekit.io/agents), connecting Murf Falcon TTS, Deepgram STT, and Google Gemini into a single conversational agent.

## How It Works

```
User speaks → [Deepgram STT] → text → [Gemini LLM] → response → [Murf Falcon TTS] → audio → User hears
```

LiveKit handles the real-time audio transport. The agent connects to LiveKit as a participant, listens for user speech, and responds with synthesized audio.

## Setup

### 1. Install dependencies

```bash
cd backend
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env.local
```

Fill in your keys in `.env.local`:

| Variable             | Where to get it                                           |
| -------------------- | --------------------------------------------------------- |
| `LIVEKIT_URL`        | [LiveKit Cloud](https://cloud.livekit.io/) → Settings     |
| `LIVEKIT_API_KEY`    | [LiveKit Cloud](https://cloud.livekit.io/) → Settings     |
| `LIVEKIT_API_SECRET` | [LiveKit Cloud](https://cloud.livekit.io/) → Settings     |
| `MURF_API_KEY`       | [murf.ai/api/dashboard](https://murf.ai/api/dashboard)    |
| `DEEPGRAM_API_KEY`   | [deepgram.com](https://console.deepgram.com/)             |
| `GOOGLE_API_KEY`     | [aistudio.google.com](https://aistudio.google.com/apikey) |

For LiveKit Cloud users, you can auto-populate LiveKit credentials:

```bash
lk cloud auth
lk app env -w -d .env.local
```

### 3. Download models

```bash
uv run python src/agent.py download-files
```

This downloads Silero VAD and the LiveKit turn detector models.

### 4. Run the agent

```bash
# Development mode (auto-reload)
uv run python src/agent.py dev

# Or test directly in your terminal (no frontend needed)
uv run python src/agent.py console

# Production
uv run python src/agent.py start
```

## Financial Services Track: Multi-Scheme Eligibility & Document Verification

DhanaMitra provides financial inclusion assistance with verified domain-specific function calling across multiple central government schemes.

### 1. Data Source & Dataset Specifications
- **Tool Name**: `check_scheme_eligibility` & `get_scheme_document_checklist`
- **Dataset Type**: **Local Verified Dataset** (`backend/src/schemes.py`) compiled from official Government of India ministry gazettes and portal guidelines.
- **Data Source**: 
  - Department of Financial Services (DFS), Ministry of Finance
  - Ministry of Housing and Urban Affairs (MoHUA)
  - Ministry of Agriculture & Farmers Welfare
  - Pension Fund Regulatory and Development Authority (PFRDA)
- **Data Update / Effective Date**: **August 2024 Official Guidelines**

### 2. Supported Government Schemes
| Scheme Name | Short / Alias | Category | Target / Eligibility Criteria | Key Benefits |
| :--- | :--- | :--- | :--- | :--- |
| **Pradhan Mantri Jan Dhan Yojana (PMJDY)** | `pmjdy`, `jan dhan` | Banking & Financial Inclusion | Indian citizens aged 10+ without a basic savings account | Zero-balance account, RuPay card with ₹2L accidental insurance, ₹10k overdraft facility |
| **Pradhan Mantri Suraksha Bima Yojana (PMSBY)** | `pmsby`, `suraksha bima` | Accident Insurance | Savings bank account holders aged 18 to 70 years | ₹20/year auto-debit; ₹2 Lakh accidental death/disability cover |
| **Pradhan Mantri Jeevan Jyoti Bima Yojana (PMJJBY)** | `pmjjby`, `jeevan jyoti` | Life Insurance | Savings bank account holders aged 18 to 50 years (cover up to 55) | ₹436/year auto-debit; ₹2 Lakh life cover for death due to any reason |
| **Atal Pension Yojana (APY)** | `apy`, `atal pension` | Pension & Retirement | Unorganized workers aged 18 to 40 years (Non-income taxpayers only) | ₹1,000 to ₹5,000 guaranteed monthly pension starting at age 60 for life |
| **Sukanya Samriddhi Yojana (SSY)** | `ssy`, `sukanya` | Girl Child Welfare | Parents/guardians of girl children aged 0 to 10 years (max 2 per family) | 8.2% p.a. sovereign guaranteed tax-free compounding returns (Sec 80C) |
| **PM SVANidhi** | `svanidhi`, `street vendor loan` | Micro-Credit | Urban street vendors and hawkers with CoV / TVC / ULB ID | Collateral-free working capital loan (₹10k -> ₹20k -> ₹50k) with 7% interest subsidy |
| **PM Mudra Yojana (PMMY)** | `pmmy`, `mudra` | MSME Business Loan | Non-farm micro & small enterprises | Collateral-free loans: Shishu (up to ₹50k), Kishore (₹50k-₹5L), Tarun (₹5L-₹10L/₹20L) |
| **PM Kisan Samman Nidhi (PM-KISAN)** | `pmkisan`, `pm kisan` | Agriculture Support | Landholding farmer families with cultivable land | ₹6,000/year direct cash transfer in 3 equal tranches of ₹2,000 |

### 3. Tool Architecture & Governance Rules
1. **Dynamic Multi-Scheme Workflow**: The agent dynamically handles inquiries across all supported schemes rather than being hardcoded to a single scheme.
2. **Missing Information Collection**: When a scheme is requested, the assistant determines the required parameters (age, occupation, taxpayer status, gender) and asks only for missing inputs before triggering the tool.
3. **No Prompt-Based Eligibility Guessing**: The LLM never determines eligibility via prompt intuition; the final evaluation comes strictly from `check_scheme_eligibility`.
4. **Mandatory Non-Guarantee Phrasing**:
   > *"Based on the information provided, you appear to meet the basic eligibility criteria. Final eligibility is subject to the applicable scheme rules and the relevant authority."*
5. **Loud Graceful Failures & Unavailable Schemes**:
   - Unavailable schemes return: *"Information for the scheme '[scheme_name]' is currently unavailable in the verified database. I cannot evaluate eligibility for schemes not listed in my official dataset."*
   - Runtime/data failure returns: *"I'm unable to retrieve the scheme information right now. Please try again later. I don't want to give you incorrect information."*

## Configuration

All configuration lives in [`src/agent.py`](src/agent.py).

### System prompt

The `SYSTEM_PROMPT` constant at the top of `agent.py` controls what your agent does. Change it to build any voice-powered use case.

#### Example prompts

**Customer Support (default):**

```
You are a friendly and efficient customer support agent for a tech company. Help users with account issues, billing questions, and product troubleshooting. Be concise, empathetic, and solution-oriented. If you don't know something, say so honestly and offer to escalate.
```

**Language Tutor:**

```
You are a patient and encouraging language tutor helping the user practice conversational Spanish. Speak primarily in Spanish but switch to English to explain grammar or vocabulary when needed. Correct mistakes gently and suggest better phrasing. Keep conversations natural and fun.
```

**AI Receptionist:**

```
You are a professional receptionist for a medical clinic. Help callers schedule appointments, answer questions about office hours and services, and take messages for doctors. Be warm but efficient. Ask for the caller's name and reason for calling upfront.
```

**Interview Coach:**

```
You are an experienced interview coach. Conduct mock interviews with the user for software engineering roles. Ask one behavioral or technical question at a time, let the user answer fully, then give specific feedback on their response — what was strong, what could improve, and a suggested reframe. Keep the tone encouraging but honest.
```

**Sales Assistant:**

```
You are a knowledgeable sales assistant for an electronics store. Help customers find the right product by asking about their needs, budget, and preferences. Compare options clearly, highlight trade-offs, and make a recommendation. Never be pushy — focus on helping the customer make the best decision for them.
```

**Fitness Coach:**

```
You are an upbeat personal fitness coach. Help users plan workouts, suggest exercises for specific muscle groups, and answer questions about form and technique. Ask about their fitness level and any injuries before recommending exercises. Keep instructions clear and motivating.
```

**Storyteller / Bedtime Narrator:**

```
You are a creative storyteller who tells original bedtime stories for children aged 4–8. Ask the child (or parent) for a character name, a favorite animal, and a setting, then weave a short, calming story. Use vivid but simple language. End each story on a peaceful, sleepy note.
```

**Meeting Summarizer:**

```
You are a meeting assistant. The user will describe what happened in a meeting or read you their notes. Summarize the key decisions, action items (with owners if mentioned), and any open questions. Be concise and structured. Ask clarifying questions if something is ambiguous.
```

**Trivia Game Host:**

```
You are an enthusiastic trivia game host. Ask the user one trivia question at a time from a mix of categories — science, history, pop culture, geography, and sports. Wait for their answer, tell them if they're right or wrong, give a brief fun fact, then move to the next question. Keep score and announce it every 5 questions.
```

**Mental Health Check-in Companion:**

```
You are a gentle, non-clinical wellness companion. Help users talk through their day, reflect on how they're feeling, and practice simple grounding exercises like deep breathing or gratitude lists. You are not a therapist — if the user expresses serious distress or mentions self-harm, gently encourage them to reach out to a professional or crisis helpline.
```

### Voice

Set the `voice` argument in the `murf.TTS(...)` call:

```python
tts=murf.TTS(
    voice="en-US-matthew",    # Change this
    style="Conversation",
    tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
    text_pacing=True
)
```

Some voice options:

| Voice ID | Description                      |
| -------- | -------------------------------- |
| `Anisha` | Indian English, female (default) |
| `Pooja`  | Indian English, female           |
| `Samar`  | Indian English, male             |
| `Amara`  | US English, female               |
| `Hazel`  | UK English, female               |
| `Bertie` | UK English, male                 |
| `Gordon` | US English, male                 |

Browse all 150+ voices: [Murf Voice Library](https://murf.ai/api/docs/voices-styles/voice-library).

### STT (Speech-to-Text)

Default is Deepgram Nova-3. Change in the `AgentSession(stt=...)` call:

```python
stt=deepgram.STT(model="nova-3")
```

### LLM

Default is Google Gemini. To switch:

- **Gemini (default):** Set `GOOGLE_API_KEY` in `.env.local`
- **OpenAI:** Set `OPENAI_API_KEY`, install `livekit-agents[openai]`, and change the `llm=` argument

## Testing

The project includes an eval suite based on the LiveKit Agents [testing framework](https://docs.livekit.io/agents/build/testing/):

```bash
uv run pytest
```

Tests are in [`tests/test_agent.py`](tests/test_agent.py) and use LLM-as-judge evaluations to verify the agent behaves correctly (friendly greetings, grounding, refusing harmful requests).

To run tests in CI, you'll need to add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as repository secrets.

## Deployment

### Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/tIVCF1?referralCode=cNjn2P&utm_medium=integration&utm_source=template&utm_campaign=generic)

Set these environment variables in Railway:

- `MURF_API_KEY`
- `DEEPGRAM_API_KEY`
- `GOOGLE_API_KEY`
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`

### Docker

A production-ready [Dockerfile](Dockerfile) is included:

```bash
docker build -t murf-voice-agent .
docker run --env-file .env.local murf-voice-agent
```

## Project Structure

```
backend/
├── src/
│   └── agent.py          # Agent entrypoint — pipeline, prompt, config
├── tests/
│   └── test_agent.py     # LLM-judged eval suite
├── .env.example           # Environment variable template
├── pyproject.toml         # Python dependencies (uv)
├── Dockerfile             # Production container
└── railway.toml           # Railway deploy config
```

## Links

- [Murf Falcon TTS Docs](https://murf.ai/api/docs/text-to-speech/streaming)
- [Murf Voice Library](https://murf.ai/api/docs/voices-styles/voice-library)
- [LiveKit Agents Docs](https://docs.livekit.io/agents)
- [Deepgram Nova-3 Docs](https://developers.deepgram.com)

## License

MIT — see [LICENSE](LICENSE).
