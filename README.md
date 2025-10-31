# Lead Qualification Voice Agent

A real-time, conversational AI voice agent designed to automate the lead qualification process. This application receives lead information from a web form, initiates a phone call via Twilio, and uses a Google Gemini-powered agent (built with the Google Agent Development Kit) to engage the lead in a natural conversation, qualify them based on the BANT framework, and schedule follow-ups.

## ✨ Features

  - **Real-Time Voice Conversation:** Utilizes Twilio Media Streams and WebSockets for low-latency, bidirectional audio streaming.
  - **Intelligent Conversation Flow:** Powered by Google Gemini and the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) to handle natural, unscripted conversations.
  - **Lead Qualification Logic:** Programmed to follow the BANT (Budget, Authority, Need, Timeline) framework to qualify leads effectively.
  - **Tool-Using Agent:** The agent can use tools to perform actions, such as scheduling a follow-up meeting in Google Calendar or saving qualification data to a CRM.
  - **Barge-In Support:** Allows users to interrupt the agent for a more natural conversational flow.
  - **Cloud-Native Architecture:** Built with FastAPI and designed for easy containerization and deployment on serverless platforms like Google Cloud Run.

## 🏛️ Architecture Overview

The application follows an event-driven, streaming architecture.

```
+--------------+          +-----------------+    
| Website Form |--------->|  1. HTTP POST   |
|  (New Lead)  |          | (Initiate Call) |   
+--------------+          +--------+--------+
                                   |
                                   | 
                                   |    
                          +--------v--------+
                          |    FastAPI App  |
                          |   (Cloud Run)   |
                          +--------+--------+
                                   |
                                   | 2. Twilio REST API Call
                                   |
                          +--------v--------+
                          |      Twilio     |
                          |                 |
                          +-----------------+
                                   |
                                   | 3. Places Phone Call
                                   |
                          +--------v--------+
                          |     Customer    |
                          |      (Lead)     |
                          +--------+--------+
                                   |
            +--------------------------------------------+
            |         4. Twilio bidirectional            |
            |            WebSocket Media Stream          |
            v                                            ^
+---------------------+                       +-------------------+     +---------------+  
| FastAPI Api         |<--------------------->| Agent Development |     | AI Platform   |
| (WebSocket Endpoint |   5. Bidirectional    | Kit (ADK Runner)  |<--->| (Gemini, STT, |
| & Handlers)         |     Audio & Events    |                   |     |  TTS)         |
+---------------------+                       +-------------------+     +---------------+
```

1.  **Initiation:** An HTTP POST request containing lead data is sent to `/api/calls/initiate`.
2.  **Call Placement:** The app uses the Twilio REST API to place an outbound phone call.
3.  **Connection:** When the lead answers, Twilio connects to the app's WebSocket endpoint (`/api/ws/twilio_stream`).
4.  **Live Conversation:** A persistent `TwilioAgentStream` handler manages the real-time, bidirectional flow of audio between Twilio and the Google ADK agent.
5.  **Intelligence:** The ADK handles the complex tasks of Speech-to-Text (STT), passing text to the Gemini-powered agent, processing the agent's textual response through Text-to-Speech (TTS), and sending the resulting audio back.

## 🛠️ Technology Stack

  - **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/)
  - **Agent Framework:** [Google Agent Development Kit (ADK)](https://www.google.com/search?q=https://github.com/google-gemini/agent-development-kit)
  - **Language Model:** [Google Gemini](https://deepmind.google/technologies/gemini/) (via Google AI Platform)
  - **Telephony & Streaming:** [Twilio Media Streams](https://www.twilio.com/docs/voice/twiml/stream)
  - **Deployment:** [Google Cloud Run](https://cloud.google.com/run) (recommended)

## 🚀 Getting Started

Follow these steps to set up and run the project locally.

### Prerequisites

  - Python 3.11+
  - A Twilio account with a provisioned phone number.
  - A Google Cloud Platform (GCP) project with the "Vertex AI API" enabled.
  - The `gcloud` command-line tool installed and configured.
  - A tool to expose your local server to the internet (e.g., [ngrok](https://ngrok.com/) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/install-and-setup/tunnel-guide/)).

### 1\. Clone the Repository

```bash
git clone https://github.com/maximilianw-google/lead-agent.git
cd lead-agent
```

### 2\. Set Up Virtual Environment

It's highly recommended to use a virtual environment.

```bash
# Create the virtual environment
python3 -m venv venv

# Activate it (macOS/Linux)
source venv/bin/activate

# Or on Windows
# venv\Scripts\activate
```

### 3\. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4\. Configure Environment Variables

Create a `.env` file in the root of the project by copying the example file.

```bash
cp .env.example .env
```

Now, edit the `.env` file and fill in your actual credentials and settings.

### 5\. Set Up Google Cloud Authentication

Authenticate your local environment so the application can access Google Cloud services.

```bash
gcloud auth application-default login
```


## 🏃 Running the Application

### Local Development

1.  **Start the FastAPI Server:**

    ```bash
    uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
    ```

2.  **Expose Your Local Server:**
    Since Twilio needs to send webhooks to your application, your local server must be accessible from the public internet. Use a tunneling tool like `ngrok`.

    ```bash
    ngrok http 8080
    ```

    Ngrok will give you a public URL (e.g., `https://random-string.ngrok.io`). **Copy this URL and paste it as the `BASE_URL` in your `.env` file.** You will need to restart your `uvicorn` server for this change to take effect.

-----

## Usage

To trigger a new qualification call, make a `POST` request to the `/api/v1/calls/initiate` endpoint. You can use `curl` or any API client.

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{
         "lead_id": "curl_lead_001",
         "first_name": "John",
         "last_name": "Doe",
         "phone_number": "+15558675309",
         "email": "john.doe@example.com",
         "call_language_code" : "it-IT",
         "product_interest": "Real-Time AI Agents"
     }' \
     https://your-public-url.com/api/initiate_call
```

**Remember to:**

  - Replace the `phone_number` with a real phone number you can answer.
  - Replace `https://your-public-url.com` with your actual ngrok or Cloud Run URL.

Upon success, you will receive a `202 Accepted` response and a phone call shortly after.

## 📁 Project Structure

```
.
├── src/
│   ├── api/                # API route definitions
│   ├── agents/             # ADK Agent definitions
│   ├── core/               # Utils and other shared libraries
│   ├── handlers/           # WebSocket logic handlers
│   ├── schemas/            # Pydantic data models
│   ├── services/           # External service clients
│   ├── tools/              # ADK Tool definitions
│   ├── config.py           # Configuration settings
│   └── main.py             # FastAPI app instantiation and router mounting
├── .env                    # Environment variables
├── requirements.txt        # Python dependencies
└── Dockerfile              # Docker container definition
```

## ☁️ Deployment

This application is container-ready and well-suited for deployment on serverless platforms like **Google Cloud Run**.

When deploying, ensure you:

1.  Build a Docker container from the provided `Dockerfile`.
2.  Push the container image to a registry like Google Artifact Registry. Default name is *lead-agent*
3.  Deploy the image as a Cloud Run service.
4.  Configure all necessary **environment variables** (as listed in `.env.example`) in the Cloud Run service settings. Remember to set `BASE_URL` to the service's own public URL - this typically will follow this pattern `https://twilio-agent-<PROJECT_NUMBER>.<REGION>.run.app`.
5.  Enable **Session Affinity** in the "Networking" tab of your Cloud Run service configuration. This is crucial for WebSocket stability.
6.  Ensure the service is configured to **"Allow unauthenticated invocations"** so that Twilio's webhooks can reach it.

Command to execute the above steps:
```
    gcloud builds submit --config=cloudbuild.yaml .
```

## 🤝 Contributing

Contributions are welcome\! Please feel free to submit a pull request or open an issue for bugs, feature requests, or improvements.

## 📝 License

This project is licensed under the MIT License - see the `LICENSE` file for details.