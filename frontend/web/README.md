# The Canary - Voice Assistant Platform

![The Canary](https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png)

*A modern, intuitive platform for managing, recording, and prioritizing voice assistants.*

---

## Features

✨ **Voice Recording & Management**
- Record voice profiles with three different speech patterns (natural, varied pace, Q&A)
- Automatic sentence-level highlighting during recording
- Drag-and-drop priority reordering
- Real-time speaker dashboard

🎙️ **Multi-Script Recording**
- Script 1: Natural Speech - Speak clearly at your normal pace
- Script 2: Varied Pace - Mix speeds and rhythms
- Script 3: Questions & Commands - Use natural Q&A intonation

📊 **Analytics Dashboard**
- Real-time voice command metrics
- Active session tracking
- Response time monitoring
- Accuracy rate tracking

🔐 **Secure Authentication**
- 10-digit phone number validation
- Secure password authentication
- Session management

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
- Linked speakers list

### 🎙️ Speaker Management (`/add-speaker`)
- Add new voice assistants
- Multi-step recording process
- Priority management (1-5)
- Drag-and-drop reordering
- Real-time speaker table

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
- `POST /api/speakers/create` - Create speaker
- `GET /api/speakers` - List all speakers
- `DELETE /api/speakers/:id` - Delete speaker
- `PATCH /api/speakers/:id/priority` - Update priority
- `PATCH /api/speakers/reorder` - Reorder speakers
- `POST /api/speakers/upload-recording` - Upload voice recording
- `GET /api/dashboard/metrics` - Get dashboard stats

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
