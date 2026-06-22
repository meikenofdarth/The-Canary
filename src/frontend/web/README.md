# The Canary - Voice Assistant Platform

![The Canary](https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png)

*A modern, intuitive platform for managing, recording, and prioritizing voice assistants.*

---

## Features

✨ **Voice Recording & Management**
- Record voice profiles with three different speech patterns
- Green checkmark visual feedback when recording completes
- Drag-and-drop priority reordering in dedicated Management page
- Real-time speaker dashboard with emoji avatars

🎙️ **Multi-Script Recording**
- Script 1: Natural Speech - Speak clearly at your normal pace
- Script 2: Varied Pace - Mix speeds and rhythms  
- Script 3: Questions & Commands - Use natural Q&A intonation
- Accessibility questions for users with speech differences

🎯 **Wake Word Customization**
- Record custom wake word phrases three times
- Visual gradient feedback when speaking
- Three-phase progress tracking with recording boxes
- Green checkmarks show completion status

📊 **Speaker Priority Management**
- Dedicated `/manage-speakers` page for full speaker list
- Drag-and-drop reordering with real-time priority updates
- Click-to-cycle status management (Active/Scheduled/Completed)
- Emoji avatar system for quick visual identification
- Individual speaker deletion with confirmation

📊 **Analytics Dashboard**
- Real-time voice command metrics
- Active session tracking
- Response time monitoring
- Accuracy rate tracking
- Quick navigation buttons to manage speakers and set up profiles

🔐 **Secure Authentication**
- 10-digit phone number validation
- Secure password authentication
- Session management

♿ **Accessibility & Inclusive Design**
- WCAG AA/AAA compliant color contrasts
- Support for users with speech variations, lisp, and speech challenges
- Accessibility mode with guided questions
- Special marker (♿) for accessibility-enabled speakers in database
- Keyboard navigation and screen reader support
- Reduced motion support

---

## Technology Stack

- **Frontend:** Next.js 16, React 19
- **Styling:** Tailwind CSS v4, shadcn/ui
- **Fonts:** Comic Relief, Manrope, Mulish, Style Script
- **Icons:** Lucide React
- **Audio:** Web Audio API, MediaRecorder
- **State Management:** React Hooks, sessionStorage

---

## Project Structure

```
/app
  /layout.tsx                    # Main layout with font imports
  /page.tsx                      # Landing page
  /add-speaker/page.tsx          # Add new speaker with voice recording
  /manage-speakers/page.tsx      # Manage speakers with priority reordering (NEW)
  /customize-wakeword/page.tsx   # Wake word customization
  /dashboard/page.tsx            # Main dashboard with analytics
  /login/page.tsx                # Login page
  /signup/page.tsx               # Signup page

/components
  /login-form.tsx                # Authentication form
  /dashboard-navbar.tsx          # Dashboard header
  /speakers-list.tsx             # Speaker list component
  /footer.tsx                    # Footer component
  /usage-chart.tsx               # Analytics chart

/styles
  /globals.css                   # Global styles, design tokens, fonts

/public
  /avatars/                      # Speaker avatar images
  /icons/                        # Custom icons
```

---

## Key Pages

### Customize Wake Word Page (`/customize-wakeword`)
**Purpose:** Allow users to record and train their custom wake word

**Features:**
- Large, centered microphone icon with gradient styling
- Real-time speaking detection with visual feedback
- Three-phase recording with progress bar
- Numbered instructions for clarity
- Accessibility-first design
- Support for users with speech differences

**API Integration Points:**
- `GET /api/wakeword/settings` - Fetch current wake word settings
- `POST /api/wakeword/session/start` - Initialize recording session
- `POST /api/wakeword/session/save-phase` - Save each phase recording
- `POST /api/wakeword/finalize` - Complete wake word setup
  /globals.css                   # Tailwind + custom styles
  /page.tsx                      # Landing page
  /login/page.tsx                # Login page
  /signup/page.tsx               # Signup page
  /dashboard/page.tsx            # Main dashboard
  /add-speaker/page.tsx          # Speaker management
  /api/                          # API routes (to be implemented)

/components
  /login-form.tsx                # Login form component
  /speakers-list.tsx             # Dashboard speakers list
  /dashboard-navbar.tsx          # Navigation bar
  /footer.tsx                    # Footer
  /usage-chart.tsx               # Analytics chart

/public
  /avatars/                      # Speaker avatar animals
    /lion.png
    /owl.png
    /fox.png
    /raven.png
    /eagle.png

/docs
  DESIGN_SYSTEM.md               # Complete design system documentation
  API_INTEGRATION_GUIDE.md       # API endpoints and integration guide
  README.md                      # This file
```

---

## Getting Started

### Prerequisites
- Node.js 18+
- npm, yarn, or pnpm

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd the-canary

# Install dependencies
pnpm install
# or
npm install

# Run development server
pnpm dev
# or
npm run dev
```

Visit `http://localhost:3000` in your browser.

---

## Key Pages

### 🏠 Landing Page (`/`)
- Hero section introducing The Canary
- Feature overview
- Call-to-action buttons
- Navigation to login/signup

### 🔑 Authentication
- **Login** (`/login`): Phone number + password
- **Signup** (`/signup`): Create new account
- Session management with sessionStorage

### 📱 Dashboard (`/dashboard`)
- Voice command metrics
- Active session tracking
- Response time stats
- Accuracy metrics
- Quick-action buttons: "Set Up Voice Profile", "Manage Speakers", "Add Speaker"

### 🎙️ Add Speaker (`/add-speaker`)
- Record voice profiles with three different speech patterns
- Script 1: Natural Speech (speak clearly)
- Script 2: Varied Pace (mix speeds and rhythms)
- Script 3: Questions & Commands (natural Q&A intonation)
- City and Country information
- Music genre preference
- Priority assignment (1-5)
- Accessibility mode for users with speech differences
- **Visual feedback:** Green checkmarks appear after each recording completes
- **Back button redirects to Dashboard**

### 📊 Manage Speakers (`/manage-speakers`) - NEW
- View all registered speakers with emoji icons
- Drag-and-drop priority reordering
- Click-to-cycle status badges (Active → Scheduled → Completed)
- Delete speakers individually
- Real-time priority recalculation
- Quick "Add New Speaker" button

### 🎯 Customize Wake Word (`/customize-wakeword`)
- Record custom wake word phrases three times
- Visual gradient feedback when speaking
- Three-phase progress tracking with progress boxes
- Recording boxes show green checkmarks when complete
- Accessibility-first interface for users with speech differences

---

## Design System

The Canary uses a cohesive design system with carefully selected colors, typography, and spacing.

### Color Palette
- **Primary:** Yellow (#fcd34d) - Energy, positivity
- **Neutral:** Whites, grays, blacks - Clean, professional
- **Status:** Green (active), Blue (scheduled), Gray (completed)

### Typography
- **Comic Relief** - Brand headings (playful, memorable)
- **Manrope** - Professional titles and headers
- **Mulish** - Form labels and friendly copy
- **Style Script** - Decorative accents

### Components
- Rounded buttons with hover shadows
- Card-based layouts
- Responsive grid system
- Accessible form inputs
- Color-coded status badges

**→ See `DESIGN_SYSTEM.md` for complete design documentation**

---

## API Integration

All buttons (except login/signup) have API integration comments marked with `// TODO: API Integration`.

### Available Endpoints (to be implemented)
- `POST /api/auth/login` - User authentication
- `GET /api/auth/session` - Session validation
- `POST /api/speakers/create` - Create speaker with voice recordings
- `GET /api/speakers` - List all speakers with priority
- `DELETE /api/speakers/:id` - Delete speaker
- `PATCH /api/speakers/:id/priority` - Update speaker priority
- `PUT /api/speakers/reorder` - Batch reorder speakers (drag-and-drop)
- `PATCH /api/speakers/:id/status` - Update speaker status (active/scheduled/completed)
- `POST /api/speakers/upload-recording` - Upload voice recording blob
- `GET /api/dashboard/metrics` - Get dashboard stats
- `POST /api/wakeword/save` - Save custom wake word recording

**→ See `API_INTEGRATION_GUIDE.md` for detailed endpoint specifications**

---

## Voice Recording Flow

### Scripts & Validation
1. **Script Selection** - Choose natural speech, varied pace, or Q&A
2. **Microphone Permission** - Browser requests audio access
3. **Real-time Highlighting** - Sentences highlight in red as you speak
4. **Recording Confirmation** - Stop recording and review audio

### Multi-Step Process
- Scripts 1 & 2: Mark as "Add Voice" (preliminary recordings)
- Script 3: Confirm and officially "Add Speaker"
- Automatic priority assignment (default: 1)
- Can reorder speakers after creation

---

## Performance Optimizations

✅ **Font Optimization**
- Google Fonts with `display=swap` strategy
- Zero render-blocking CSS

✅ **Image Optimization**
- Responsive sizing (10-80px avatars)
- Lazy loading support
- Optimized logo variants

✅ **CSS Framework**
- Tailwind CSS v4 (on-demand generation)
- Only necessary utilities shipped
- Minimal bundle size

✅ **React Optimizations**
- Client-side hooks for state management
- sessionStorage for data syncing
- Efficient re-renders

---

## Accessibility

✓ **WCAG AA Compliance**
- High contrast ratios (7:1+)
- Semantic HTML structure
- ARIA labels and roles
- Keyboard navigation support
- Focus indicators
- Proper form associations

---

## Development Guidelines

### Adding New Features

1. **Component Structure**
   - Keep components focused and reusable
   - Use TypeScript interfaces for props
   - Implement proper error handling

2. **Styling**
   - Use Tailwind utility classes
   - Reference `DESIGN_SYSTEM.md` for color/spacing
   - Maintain consistent spacing scale

3. **API Integration**
   - Add `// TODO: API Integration` comments
   - Include payload/response specifications
   - Use error handling patterns from guide

4. **Testing**
   - Test on mobile, tablet, desktop
   - Verify accessibility with screen readers
   - Check performance metrics

---

## API Integration for Developers

### For Claude (or other AI assistants)

All API integration points are clearly marked in the codebase:

```typescript
// TODO: API Integration - [Description]
// POST /api/endpoint
// Payload: { ... }
// Response: { ... }
```

Use the `API_INTEGRATION_GUIDE.md` file to understand:
- All required endpoints
- Data models and schemas
- Authentication strategy
- Error handling patterns
- Security best practices

This makes it easy to connect the frontend to any backend API.

---

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Android)

---

## Future Enhancements

🔮 **Planned Features**
- Dark mode toggle
- User preferences/settings
- Advanced analytics
- Voice command templates
- Multi-language support
- Real-time notifications
- Export/backup functionality
- Admin dashboard

---

## Security Notes

⚠️ **Important Security Considerations**
- Never expose API tokens in client code
- Use httpOnly cookies for token storage
- Implement CSRF protection
- Validate all inputs server-side
- Hash passwords using bcrypt
- Use HTTPS in production
- Implement proper CORS headers
- Rate limit authentication attempts

---

## Troubleshooting

### Microphone Not Working
- Check browser permissions (Settings > Privacy & Security)
- Try a different browser
- Verify microphone is plugged in and working
- Reload the page

### Recordings Not Saving
- Check storage quota (sessionStorage limited to ~5-10MB)
- Verify network connection for API calls
- Check browser console for errors
- Clear browser cache and try again

### Styling Issues
- Clear Tailwind cache: `rm -rf .next`
- Rebuild: `pnpm dev`
- Check for conflicting CSS rules
- Verify font imports in layout.tsx

---

## Contributing

Contributions are welcome! Please:
1. Create a feature branch
2. Follow the design system guidelines
3. Add API integration comments
4. Test thoroughly
5. Submit a pull request

---

## License

Proprietary - The Canary Voice Assistant Platform

---

## Support

For issues, feature requests, or documentation improvements:
- Create an issue on GitHub
- Contact: support@thecanary.com

---

**The Canary** - Bringing voice to life 🐦

*Last Updated: June 16, 2026*
