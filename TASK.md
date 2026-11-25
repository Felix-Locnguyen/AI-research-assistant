TODO LIST - AI Assistant (FastAPI + Telegram/Zalo/Messenger)

Priority: High / Medium / Low

EPIC 01 - Project Initialization

Deliverable: FastAPI backend starts up reliably.

[ ] T01 [High] Initialize Project - create the project directory structure
[ ] T02 [High] Setup Environment - create virtual environment, install dependencies
[ ] T03 [High] Configure Environment - set up .env and .env.example
[ ] T04 [High] Setup FastAPI - initialize the app and entry point
[ ] T05 [Medium] Setup Docker - create Dockerfile and docker-compose
[ ] T06 [Medium] Setup Logging - configure logging and exception handling
EPIC 02 - Database & User Management

Deliverable: Database can store and retrieve user information.

[ ] T07 [High] Database Connection - connect to PostgreSQL (SQLAlchemy async)
[ ] T08 [High] User Model - design the users table
[ ] T09 [High] Preference Model - design the user_preferences table
[ ] T10 [High] Conversation Model - design conversations and messages tables
[ ] T11 [High] Memory Model - design the memories table
[ ] T12 [High] Reminder Model - design the reminders table
[ ] T13 [High] Subscription Model - design the subscriptions table
[ ] T14 [High] Article Model - design the articles table
[ ] T15 [Medium] Database Migration - configure Alembic
[ ] T16 [High] User Repository - CRUD for users and preferences
EPIC 03 - Telegram Integration

Deliverable: Users can send messages and receive replies via Telegram.

[ ] T17 [High] Create Telegram Bot - create the bot and get the token
[ ] T18 [High] Webhook Integration - receive messages via webhook
[ ] T19 [High] Message Normalization - convert messages into a common format
[ ] T20 [High] User Identification - identify Telegram users
[ ] T21 [High] Message Handler - process incoming messages
[ ] T22 [High] Response Handler - send replies back to Telegram
[ ] T23 [Medium] Error Handling - handle send/receive errors
EPIC 04 - AI Conversation

Deliverable: AI understands requests, maintains conversations, and calls tools.

[ ] T24 [High] LLM Client - build the LLM API connection module
[ ] T25 [High] System Prompt - design the assistant prompt
[ ] T26 [High] Intent Classification - classify user intent
[ ] T27 [High] Conversation Handler - orchestrate the conversation flow
[ ] T28 [High] Context Builder - build context for each LLM call
[ ] T29 [High] Tool Calling - allow the AI to call tools
[ ] T30 [High] Conversation History - store conversation history
EPIC 05 - Memory Management

Deliverable: AI remembers preferences and reuses them in later sessions.

[x] T31 [High] Short-term Memory - manage temporary conversation state
[x] T32 [High] Memory Extraction - extract important information from conversations
[x] T33 [High] Memory Validation - validate information before saving
[x] T34 [High] Memory Update - add, edit, and update memories
[x] T35 [High] Memory Retrieval - retrieve relevant memories
[x] T36 [Medium] Memory Cleanup - handle expired and duplicate memories
[x] T37 [Medium] Context Generation - generate Markdown context from stored data
EPIC 06 - Research Agent

Deliverable: Users can ask the AI to search, filter, and synthesize information.

[x] T38 [High] Search Integration - integrate an Internet search tool
[x] T39 [Medium] RSS Integration - collect information from RSS feeds
[x] T40 [High] Search Query Generator - generate queries based on user preferences
[x] T41 [High] Content Extractor - extract article content
[x] T42 [High] Duplicate Detection - detect duplicate articles
[x] T43 [High] Relevance Filter - filter content by user preferences
[x] T44 [High] Content Summarizer - summarize content with an LLM
[x] T45 [High] Source Verification - check source and publication date
[x] T46 [High] Article Storage - store articles in PostgreSQL
[x] T47 [High] Research Result Formatter - format research results
EPIC 07 - Reminder System

Deliverable: Users receive notifications at the scheduled time.

[x] T48 [High] Reminder CRUD - create, view, edit, delete reminders
[x] T49 [High] Natural Language Parsing - understand reminder times from messages
[x] T50 [High] Scheduler - background job that periodically checks reminders
[x] T51 [High] Notifier - send notifications to the user's channel
[x] T52 [Medium] Recurring Reminders - support daily and weekly repeats
[x] T53 [Medium] Timezone Handling - handle user timezones
EPIC 08 - Additional Channels (Zalo & Messenger)

Deliverable: The same processing flow works across all 3 channels.

[x] T54 [High] Channel Base Interface - standardize a common interface for all channels
[x] T55 [High] Zalo Integration - Zalo OA webhook, send/receive messages
[x] T56 [Medium] Messenger Integration - Facebook Messenger webhook, send/receive messages
[x] T57 [Medium] Channel Adapter Test - test each channel with the standard message format
EPIC 09 - Background Queue & Scheduling

Deliverable: System stays stable under many concurrent messages.

[x] T58 [High] Task Queue - set up an async message processing queue
[x] T59 [Medium] Retry & Dead Letter - automatic retries and failed job handling
[x] T60 [Medium] Rate Limiting - limit the frequency of LLM and external API calls
EPIC 10 - Testing

Deliverable: Green test suite; code changes do not break existing features.

[x] T61 [High] Unit Tests - per-module tests (repository, handler, memory, ...)
[x] T62 [High] API Tests - test FastAPI endpoints with TestClient
[x] T63 [Medium] Channel Mock Test - mock Telegram/Zalo/Messenger for integration tests
[x] T64 [Medium] CI Setup - run tests automatically (GitHub Actions)
EPIC 11 - Deployment & Operations

Deliverable: Project installs on another machine and runs reliably.

[x] T65 [High] Compose Full Stack - Docker Compose with app + PostgreSQL + queue
[x] T66 [High] Secrets Management - manage secrets safely (never commit .env)
[x] T67 [Medium] Health Check - system status endpoint
[x] T68 [Medium] Production README - installation, configuration, and run guide
[x] T69 [Low] Monitoring & Alerts - centralized logging and error alerts
Suggested Sprint Order
Sprint	Epics	Outcome
1	01 + 02	Backend runs, DB stores users
2	03 + 04	Chat with the AI via Telegram
3	05	AI has long-term memory
4	06	Research Agent
5	07 + 09	Reminders + background queue
6	08	Add Zalo and Messenger
7	10 + 11	Testing, CI, deployment