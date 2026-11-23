# Nexus AI – Development Roadmap

## 1. Project Overview

**Nexus AI** là trợ lý AI cá nhân có khả năng giao tiếp, ghi nhớ thông tin người dùng, tìm kiếm dữ liệu trên Internet, phân tích nội dung và chủ động gửi thông tin qua các nền tảng như Telegram, Zalo và Messenger.

### Core Features

- Multi-channel Communication
- AI Conversation
- Context Management
- Long-term Memory
- Research Agent
- Automated Information Retrieval
- Reminder System
- Scheduled Notifications

---

# 2. Development Tasks

## EPIC 01 – Project Initialization

**Mục tiêu:** Khởi tạo môi trường và cấu trúc dự án.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T01 | Initialize Project | Tạo cấu trúc thư mục dự án | High |
| T02 | Setup Environment | Tạo virtual environment, cài dependencies | High |
| T03 | Configure Environment | Thiết lập `.env`, `.env.example` | High |
| T04 | Setup FastAPI | Khởi tạo FastAPI và entry point | High |
| T05 | Setup Docker | Tạo Dockerfile và docker-compose | Medium |
| T06 | Setup Logging | Cấu hình logging và xử lý exception | Medium |

**Deliverable:** Backend FastAPI có thể khởi chạy ổn định.

---

## EPIC 02 – Database & User Management

**Mục tiêu:** Quản lý người dùng và dữ liệu.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T07 | Database Connection | Kết nối PostgreSQL | High |
| T08 | User Model | Thiết kế bảng users | High |
| T09 | Preference Model | Thiết kế user_preferences | High |
| T10 | Conversation Model | Thiết kế conversations và messages | High |
| T11 | Memory Model | Thiết kế bảng memories | High |
| T12 | Reminder Model | Thiết kế bảng reminders | High |
| T13 | Subscription Model | Thiết kế bảng subscriptions | High |
| T14 | Article Model | Thiết kế bảng articles | High |
| T15 | Database Migration | Cấu hình Alembic | Medium |
| T16 | User Repository | CRUD người dùng và sở thích | High |

**Deliverable:** Database có thể lưu và truy xuất thông tin người dùng.

---

## EPIC 03 – Telegram Integration

**Mục tiêu:** Cho phép người dùng giao tiếp với AI qua Telegram.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T17 | Create Telegram Bot | Tạo bot và lấy token | High |
| T18 | Webhook Integration | Tiếp nhận tin nhắn qua webhook | High |
| T19 | Message Normalization | Chuẩn hóa tin nhắn thành định dạng chung | High |
| T20 | User Identification | Xác định người dùng Telegram | High |
| T21 | Message Handler | Xử lý tin nhắn đầu vào | High |
| T22 | Response Handler | Gửi phản hồi về Telegram | High |
| T23 | Error Handling | Xử lý lỗi gửi và nhận tin | Medium |

**Deliverable:** Người dùng có thể nhắn tin và nhận phản hồi từ hệ thống.

---

## EPIC 04 – AI Conversation

**Mục tiêu:** Xây dựng trợ lý có khả năng hiểu và xử lý yêu cầu.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T24 | LLM Client | Tạo module kết nối LLM API | High |
| T25 | System Prompt | Thiết kế prompt cho trợ lý | High |
| T26 | Intent Classification | Phân loại ý định người dùng | High |
| T27 | Conversation Handler | Điều phối quá trình hội thoại | High |
| T28 | Context Builder | Xây dựng context cho mỗi lần gọi LLM | High |
| T29 | Tool Calling | Cho phép AI gọi các công cụ | High |
| T30 | Conversation History | Lưu lịch sử hội thoại | High |

**Deliverable:** AI có thể hiểu yêu cầu, duy trì hội thoại và gọi công cụ.

---

## EPIC 05 – Memory Management

**Mục tiêu:** Xây dựng hệ thống bộ nhớ cho người dùng.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T31 | Short-term Memory | Quản lý hội thoại tạm thời | High |
| T32 | Memory Extraction | Trích xuất thông tin quan trọng từ hội thoại | High |
| T33 | Memory Validation | Kiểm tra thông tin trước khi lưu | High |
| T34 | Memory Update | Thêm, sửa, cập nhật ký ức | High |
| T35 | Memory Retrieval | Truy xuất ký ức liên quan | High |
| T36 | Memory Cleanup | Xử lý ký ức hết hạn và trùng lặp | Medium |
| T37 | Context Generation | Tạo context Markdown từ dữ liệu đã lưu | Medium |

**Deliverable:** AI có thể ghi nhớ sở thích và sử dụng lại thông tin ở các phiên sau.

---

## EPIC 06 – Research Agent

**Mục tiêu:** Tự động tìm kiếm và phân tích thông tin.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T38 | Search Integration | Tích hợp công cụ tìm kiếm Internet | High |
| T39 | RSS Integration | Thu thập thông tin từ RSS | Medium |
| T40 | Search Query Generator | Tạo truy vấn dựa trên sở thích người dùng | High |
| T41 | Content Extractor | Trích xuất nội dung bài viết | High |
| T42 | Duplicate Detection | Phát hiện bài viết trùng lặp | High |
| T43 | Relevance Filter | Lọc nội dung theo sở thích | High |
| T44 | Content Summarizer | Tóm tắt nội dung bằng LLM | High |
| T45 | Source Verification | Kiểm tra nguồn và thời gian xuất bản | High |
| T46 | Article Storage | Lưu bài viết vào PostgreSQL | High |
| T47 | Research Result Formatter | Định dạng kết quả nghiên cứu | High |

**Deliverable:** Người dùng có thể yêu cầu AI tìm kiếm, lọc và tổng hợp thông tin.

---

## EPIC 07 – Reminder System

**Mục tiêu:** Cho phép người dùng tạo và quản lý lịch nhắc.

| ID | Task | Nội dung | Priority |
|---|---|---|---|
| T48 | Reminder CRUD | Tạo, xem,