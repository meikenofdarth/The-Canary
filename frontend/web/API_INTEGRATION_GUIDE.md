# The Canary - API Integration Guide for Developers

## Overview
This document provides API integration points and guidelines for connecting the frontend to backend services. All TODOs in the codebase are marked with `// TODO: API Integration`.

---

## Core API Endpoints

### 1. Authentication Endpoints

#### Login
```
POST /api/auth/login
Headers: Content-Type: application/json
Payload: {
  phone: string (10 digits, format: +1XXXXXXXXXX or XXXXXXXXXX),
  password: string (minimum 8 characters)
}
Response (200): {
  userId: string (UUID),
  token: string (JWT or session token),
  expiresIn: number (seconds, default: 3600),
  authenticated: boolean (true),
  user: {
    id: string,
    phone: string,
    createdAt: ISO8601 timestamp
  }
}
Error (400/401): {
  error: string (descriptive error message),
  code: string (ERROR_CODE)
}
```

#### Signup
```
POST /api/auth/signup
Headers: Content-Type: application/json
Payload: {
  phone: string,
  password: string,
  confirmPassword: string
}
Response (201): Same as login
Error (400/422): Validation errors
```

#### Logout
```
POST /api/auth/logout
Headers: Authorization: Bearer <token>
Response (200): { success: boolean, loggedOut: true }
```

#### Session Check
```
GET /api/auth/session
Headers: Authorization: Bearer <token> (or use httpOnly cookie)
Response (200): {
  userId: string,
  email: string,
  authenticated: boolean,
  expiresAt: ISO8601 timestamp
}
Error (401): { authenticated: false }
```

---

### 2. Speaker Management Endpoints

#### Create Speaker
```
POST /api/speakers/create
Headers: Authorization: Bearer <token>
         Content-Type: application/json
Payload: {
  name: string (1-100 characters),
  priority: number (1-5),
  recordingId: string (from upload-recording response),
  avatar: string (URL or predefined avatar identifier)
}
Response (201): {
  id: string (UUID),
  name: string,
  priority: number,
  avatar: string,
  status: 'scheduled' | 'active' | 'completed',
  recordingId: string,
  createdAt: ISO8601 timestamp,
  updatedAt: ISO8601 timestamp
}
Error (400/409): Validation or duplicate speaker
```

#### List All Speakers
```
GET /api/speakers?page=1&limit=20&sortBy=priority
Headers: Authorization: Bearer <token>
Query Params:
  page: number (default: 1)
  limit: number (default: 20, max: 100)
  sortBy: 'priority' | 'created' | 'name' (default: 'priority')
  order: 'asc' | 'desc' (default: 'desc')
Response (200): {
  speakers: Speaker[],
  pagination: {
    page: number,
    limit: number,
    total: number,
    pages: number
  }
}
```

#### Get Speaker by ID
```
GET /api/speakers/:id
Headers: Authorization: Bearer <token>
Response (200): Speaker object
Error (404): { error: 'Speaker not found' }
```

#### Update Speaker Priority
```
PATCH /api/speakers/:id/priority
Headers: Authorization: Bearer <token>
         Content-Type: application/json
Payload: {
  priority: number (1-5)
}
Response (200): {
  id: string,
  priority: number,
  updatedAt: ISO8601 timestamp
}
```

#### Reorder Speakers (Drag & Drop)
```
PATCH /api/speakers/reorder
Headers: Authorization: Bearer <token>
         Content-Type: application/json
Payload: {
  draggedId: string,
  targetId: string,
  draggedPriority: number,
  targetPriority: number
}
Response (200): {
  speakers: Speaker[],
  reorderedAt: ISO8601 timestamp
}
```

#### Delete Speaker
```
DELETE /api/speakers/:id
Headers: Authorization: Bearer <token>
Response (200): {
  success: boolean,
  deletedId: string,
  deletedAt: ISO8601 timestamp
}
Error (404): { error: 'Speaker not found' }
```

---

### 3. Voice Recording Endpoints

#### Upload Recording
```
POST /api/speakers/upload-recording
Headers: Authorization: Bearer <token>
         Content-Type: multipart/form-data
Form Data:
  audio: File (Blob, webm/mp3/wav format)
  speakerName: string
  scriptId: number (1, 2, or 3)
Response (200): {
  recordingId: string (UUID),
  speakerName: string,
  scriptId: number,
  duration: number (seconds),
  fileSize: number (bytes),
  processedAt: ISO8601 timestamp,
  status: 'uploaded' | 'processing' | 'ready'
}
Error (400/413): File validation or size limit (max: 25MB)
```

#### Prepare Recording Session
```
POST /api/speakers/recording-session
Headers: Authorization: Bearer <token>
         Content-Type: application/json
Payload: {
  speakerName: string,
  scriptId: number
}
Response (200): {
  sessionId: string,
  startedAt: ISO8601 timestamp,
  expiresAt: ISO8601 timestamp (300 seconds TTL)
}
```

#### Download Recording
```
GET /api/speakers/recording/:recordingId/download
Headers: Authorization: Bearer <token>
Response: File (binary stream)
Headers: Content-Type: audio/webm
         Content-Disposition: attachment; filename="speaker-recording.webm"
```

---

### 4. Dashboard Endpoints

#### Get Dashboard Metrics
```
GET /api/dashboard/metrics
Headers: Authorization: Bearer <token>
Query Params:
  period: 'day' | 'week' | 'month' (default: 'month')
Response (200): {
  commandsProcessed: number,
  activeSessions: number,
  avgResponseTime: number (milliseconds),
  accuracyRate: number (0-100, percentage),
  topSpeakers: Speaker[],
  trend: {
    commands: { date: string, count: number }[],
    sessions: { date: string, count: number }[]
  },
  generatedAt: ISO8601 timestamp
}
```

#### Get Speaker Performance
```
GET /api/speakers/:id/performance
Headers: Authorization: Bearer <token>
Query Params:
  period: 'day' | 'week' | 'month' (default: 'month')
Response (200): {
  speakerId: string,
  speakerName: string,
  metrics: {
    recordingsProcessed: number,
    totalDuration: number (seconds),
    accuracy: number (0-100),
    avgResponseTime: number (milliseconds),
    topCommands: string[]
  }
}
```

---

## Data Models

### Speaker Object
```typescript
interface Speaker {
  id: string;                              // UUID
  userId: string;                          // Owner user ID
  name: string;                            // Speaker name (1-100 chars)
  avatar: string;                          // URL or identifier
  priority: number;                        // 1-5 (5 = highest)
  status: 'active' | 'scheduled' | 'completed';
  recordingId?: string;                    // Latest recording reference
  description?: string;                    // Optional notes
  createdAt: string;                       // ISO8601 timestamp
  updatedAt: string;                       // ISO8601 timestamp
}
```

### Recording Object
```typescript
interface Recording {
  id: string;
  speakerId?: string;
  speakerName: string;
  scriptId: number;                        // 1, 2, or 3
  duration: number;                        // Seconds
  fileSize: number;                        // Bytes
  url: string;                             // Streaming URL
  status: 'uploading' | 'processing' | 'ready' | 'failed';
  processedAt?: string;                    // When processing completed
  createdAt: string;
}
```

### User Object
```typescript
interface User {
  id: string;                              // UUID
  phone: string;                           // Formatted phone number
  password: string;                        // Hashed (never expose)
  createdAt: string;
  updatedAt: string;
  lastLogin?: string;
}
```

---

## Implementation Notes for Claude

### File Locations with API Comments
1. **`/app/add-speaker/page.tsx`**
   - Line ~97: Recording session preparation
   - Line ~165: Speaker creation with API context
   - Line ~217: Speaker deletion
   - Line ~228: Priority updates
   - Line ~245: Drag & drop reordering
   - Line ~107: Recording upload

2. **`/app/dashboard/page.tsx`**
   - Line ~19: Session validation
   - Line ~82: Dashboard metrics fetching

3. **`/components/login-form.tsx`**
   - Line ~28: User authentication
   - NOTE: Login/Signup APIs are for reference. Do NOT implement in frontend client code.

### Authentication Strategy
- Use **httpOnly cookies** for secure token storage (preferred)
- OR use **sessionStorage** for development (current implementation)
- Always validate tokens server-side
- Implement CSRF protection for state-changing operations

### Error Handling Pattern
```typescript
try {
  const response = await fetch('/api/endpoint', {
    method: 'POST',
    headers: { 
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json' 
    },
    body: JSON.stringify(payload)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || `HTTP ${response.status}`);
  }
  
  const data = await response.json();
  return data;
} catch (error) {
  console.error('API Error:', error);
  // Show user-friendly error message
  setError(error.message);
}
```

### File Upload Pattern
```typescript
const formData = new FormData();
formData.append('audio', audioBlob);
formData.append('speakerName', newSpeakerName);
formData.append('scriptId', selectedScript);

const response = await fetch('/api/speakers/upload-recording', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData
});
```

### Session Syncing
- Current implementation uses `sessionStorage` for speaker data
- Replace with API calls for production
- Implement real-time sync using WebSockets for live updates

---

## API Rate Limiting

- **Default Limits:**
  - 100 requests per minute per user
  - 10 MB per file upload
  - 300-second session expiry

- **Headers in Response:**
  - `X-RateLimit-Limit: 100`
  - `X-RateLimit-Remaining: 97`
  - `X-RateLimit-Reset: 1718546400`

---

## CORS Configuration

```
Allowed Origins: https://localhost:3000, https://canary.example.com
Allowed Methods: GET, POST, PATCH, DELETE, OPTIONS
Allowed Headers: Content-Type, Authorization
Credentials: true (for httpOnly cookies)
```

---

## Security Checklist

- [ ] All endpoints require Authorization header (except /auth/login, /auth/signup)
- [ ] Validate phone number format (10 digits)
- [ ] Validate password strength (min 8 chars, mix of types)
- [ ] Hash passwords using bcrypt or similar (server-side only)
- [ ] Use HTTPS for all production requests
- [ ] Implement CSRF tokens for state-changing operations
- [ ] Rate limit authentication attempts (5 per minute)
- [ ] Sanitize and validate all user inputs
- [ ] Use prepared statements to prevent SQL injection
- [ ] Implement proper CORS headers
- [ ] Set secure and httpOnly cookies
- [ ] Implement proper logging without exposing sensitive data

---

## Testing API Endpoints

### Using cURL
```bash
# Login
curl -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"5551234567","password":"securepass123"}'

# Create Speaker
curl -X POST http://localhost:3000/api/speakers/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Speaker","priority":3,"recordingId":"rec_123"}'

# Get Speakers
curl -X GET "http://localhost:3000/api/speakers?page=1&limit=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Using Postman
Import the Postman collection for full API testing (see `/api-collection.json` if provided).

---

## Next Steps for Integration

1. Create backend API routes in `/app/api/` directory
2. Implement authentication middleware
3. Connect to database (PostgreSQL recommended)
4. Add input validation and sanitization
5. Implement comprehensive error handling
6. Set up logging and monitoring
7. Create database migrations
8. Test all endpoints thoroughly
9. Deploy to staging environment
10. Performance testing and optimization

---

**Last Updated:** 2026-06-16
**Version:** 1.0
**Maintained By:** The Canary Development Team
