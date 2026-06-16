# The Canary - Voice Assistant Platform
## Design System & UI Documentation

---

## 1. Brand Identity

### Application Name
**The Canary** - A voice assistant management platform for recording, managing, and prioritizing voice assistants.

### Logo
- **Type:** Yellow bird illustration (Canary bird)
- **URL:** `https://hebbkx1anhila5yf.public.blob.vercel-storage.com/logo-rod6oexWJWuQxyR1VHbFvYyBq59vIN.png`
- **Usage:** Header navigation, landing page hero, authentication pages, dashboard navbar
- **Size Variants:**
  - Logo-only (navbar): 32x32px (`h-8 w-8`)
  - Hero section: 80x80px (`h-20 w-20`)
  - Landing page: 64x64px (`h-16 w-16`)

---

## 2. Color Palette

### Primary Colors
- **Primary (Yellow):** `#fcd34d`
  - Used for: CTA buttons, links, active states, accents
  - Hover state: Adds shadow effect (`hover:shadow-lg hover:shadow-primary/40`)
  - Alternative class: `bg-primary`, `text-primary`, `border-primary`

- **Primary Foreground:** `#000000` (black text on primary)
  - Used for text on primary-colored backgrounds
  - Ensures high contrast and accessibility

### Neutral Colors
- **Background:** CSS custom property `--background` (light off-white)
- **Foreground:** CSS custom property `--foreground` (dark gray/black text)
- **Card:** CSS custom property `--card` (white for cards)
- **Secondary:** CSS custom property `--secondary` (light gray for subtle backgrounds)
- **Border:** CSS custom property `--border` (subtle divider lines)
- **Muted Foreground:** CSS custom property `--muted-foreground` (lighter gray text)

### Status Colors
- **Active/Success:** `bg-green-100 text-green-800` or `bg-green-500`
- **Scheduled:** `bg-blue-100 text-blue-800` or `bg-blue-500`
- **Completed:** `bg-gray-100 text-gray-800`
- **Error/Danger:** `bg-red-500` (for stop recording button)

### Semantic Utilities
- **Ring/Focus:** `ring-2 ring-primary/20` (focus states for accessibility)
- **Shadow:** `shadow-sm`, `shadow-lg` for depth

---

## 3. Typography System

### Font Families

#### Primary Font Stack
- **Font Name:** Comic Relief
- **Weight:** 400 (regular), 700 (bold)
- **Usage:** All heading tags (h1-h6), main brand copy, emphasis text
- **CSS Variable:** `--font-comic-relief`
- **Google Fonts URL:** Imported in `/app/layout.tsx`
- **Example:** "The Canary", "Manage Speakers", "Built for Modern Teams"

#### Secondary Font - Heading/Titles
- **Font Name:** Manrope
- **Weight:** 200–800 (variable)
- **Usage:** Page titles, section headers, professional headings
- **CSS Variable:** `--font-manrope`
- **Class:** `.font-manrope`
- **Example:** "Manage Speakers" page title

#### Tertiary Font - Form Labels & Body
- **Font Name:** Mulish
- **Weight:** 200–1000 (variable), italic support
- **Usage:** Form labels, input hints, smaller body text
- **CSS Variable:** `--font-mulish`
- **Class:** `.font-mulish`
- **Example:** "Register New Speaker" form heading

#### Decorative Font
- **Font Name:** Style Script
- **Weight:** 400
- **Usage:** Decorative elements, step indicators, accent typography
- **CSS Variable:** `--font-style-script`
- **Class:** `.font-style-script`
- **Fallback:** `cursive`

#### Alternative Decorative Font
- **Font Name:** Gloria Hallelujah
- **Weight:** 400
- **Usage:** Fun, playful accents
- **CSS Variable:** `--font-gloria`
- **Class:** `.font-gloria`
- **Fallback:** `cursive`

#### Alternative Sans Font
- **Font Name:** Elms Sans
- **Weight:** 100–900 (variable), italic support
- **Usage:** Alternative sans-serif for specific sections
- **CSS Variable:** Not directly used yet
- **Class:** `.font-elms-sans`

### Typography Scale

| Element | Font | Size | Weight | Line Height | Example |
|---------|------|------|--------|------------|---------|
| Page Title (h1) | Comic Relief | 32px (`text-3xl`) | 700 | 1.2 | "Manage Speakers" |
| Section Header (h2) | Mulish | 20px (`text-xl`) | 700 | 1.3 | "Register New Speaker" |
| Button Text | Comic Relief/Manrope | 14px–16px | 600 (semibold) | 1.5 | "Confirm Add Voice" |
| Body Text | System Sans | 14px–16px | 400 | 1.5 | Form labels, descriptions |
| Small Text | System Sans | 12px (`text-xs`) | 400 | 1.4 | Hints, meta information |
| Status Badge | System Sans | 12px (`text-xs`) | 600 | 1.5 | "Active", "Scheduled" |

### Text Color Usage
- **Primary Text:** `text-foreground` (dark gray/black)
- **Secondary Text:** `text-muted-foreground` (lighter gray)
- **On Primary Bg:** `text-primary-foreground` (black on yellow)
- **Accent/Links:** `text-primary` (yellow)

---

## 4. UI Components & Patterns

### Buttons

#### Primary Button (CTA)
```
Background: bg-primary (yellow)
Text Color: text-primary-foreground (black)
Padding: px-6 py-3 (desktop), px-4 py-2 (inline)
Border Radius: rounded-lg
Hover: shadow-lg shadow-primary/40
Transition: transition-all
Icon + Text: flex items-center gap-2
```

**Examples:**
- "Add Speaker" button (with microphone icon)
- "Confirm Add Voice" / "Confirm Add Speaker"
- "Start Recording" button
- "Next: Script 3" (green variant: `bg-green-600`)

#### Secondary Button (Outlined)
```
Background: transparent
Border: border-2 border-primary
Text Color: text-primary
Hover: hover:bg-primary/5
```

**Examples:**
- "Play Recording" button
- Download button

#### Icon-Only Button
```
Padding: px-4 py-3
Use Case: Download, action buttons
```

### Form Elements

#### Input Fields
```
Border: border border-border
Background: bg-secondary
Text Color: text-foreground
Placeholder: placeholder-muted-foreground
Focus: focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20
Border Radius: rounded-lg
Padding: px-4 py-2
```

#### Select Dropdowns
```
Same styling as inputs
Text: font-medium (for priority selector)
Width: w-full or fixed
```

#### Labels
```
Font: font-medium
Color: text-foreground
Size: text-sm
Margin: block (display)
```

### Cards & Containers

#### Form Container
```
Border: border border-border
Background: bg-card
Padding: p-6
Border Radius: rounded-lg
Shadow: Default (no heavy shadow)
```

#### Table Container
```
Border: border border-border
Background: bg-card
Border Radius: rounded-lg (outer)
Overflow: overflow-x-auto
```

#### Script Selection Box
```
Border: border-2 (changes on state)
Default: border-border
Selected: border-primary (yellow)
Confirmed: border-green-500 with ring-2 ring-green-300
Hover: hover:border-primary/50
Padding: p-3
Border Radius: rounded-lg
Transition: transition-all
```

### Table Styling

#### Header Row
```
Background: bg-secondary/50
Border Bottom: border-b border-border
Padding: px-6 py-4
Font: font-semibold text-sm
```

#### Data Rows
```
Border Bottom: border-b border-border (divide-y divide-border on tbody)
Padding: px-6 py-4
Hover: hover:bg-secondary/40 cursor-move
Transition: transition-all
```

#### Drag State
```
Dragging: opacity-50 bg-primary/10
Default: cursor-move
```

### Status Badges

#### Badge Styles
```
Padding: px-3 py-1
Font: font-medium text-xs
Border Radius: rounded-full

Colors:
- Active: bg-green-100 text-green-800 / bg-green-500 text-white
- Scheduled: bg-blue-100 text-blue-800 / bg-blue-500 text-white
- Completed: bg-gray-100 text-gray-800
```

### Recording Indicators

#### Script Highlighting
```
Default: bg-border text-foreground
Recording/Highlighted: bg-red-500 text-white
Padding: px-3 py-2
Border Radius: rounded
Transition: transition-all
Font: font-medium
```

#### Recording Button
```
Active: bg-red-500 animate-pulse
Hover: hover:shadow-lg hover:shadow-red-500/40
```

---

## 5. Layout & Spacing

### Spacing Scale (Tailwind)
- **xs:** 2px (0.125rem)
- **sm:** 4px (0.25rem)
- **md:** 8px (0.5rem)
- **lg:** 16px (1rem)
- **xl:** 24px (1.5rem)
- **2xl:** 32px (2rem)
- **3xl:** 48px (3rem)
- **4xl:** 64px (4rem)

### Container Width
```
max-w-7xl (80rem / 1280px)
Padding: px-6 (desktop), px-4 (mobile)
Margin: mx-auto (centered)
```

### Section Spacing
```
Page Header: py-6, border-b, bg-card
Main Content: py-8
Action Buttons Row: mb-8
Form Container: mb-8
Table: Default spacing
```

### Gap & Row Spacing
```
Flex Gaps: gap-2 (small), gap-3 (medium), gap-4 (large)
Grid Gaps: gap-6 (default for 2-column grid)
Table Rows: py-4 (vertical padding for readability)
Script List: space-y-2 (between script boxes)
Form Sections: space-y-4 (between form groups)
```

---

## 6. Responsive Design

### Breakpoints (Tailwind)
- **sm:** 640px
- **md:** 768px
- **lg:** 1024px
- **xl:** 1280px
- **2xl:** 1536px

### Grid Responsive Pattern
```
Grid: md:grid-cols-2 (2 columns on tablet+)
On smaller screens: 1 column (default)
Gap: gap-6 (between columns)
```

### Navigation
- Mobile-first approach
- Hamburger menu (for future mobile implementation)
- Desktop navbar: sticky/fixed with logo

---

## 7. Icons

### Icon Library
- **Provider:** Lucide React
- **Size:** 16px (`h-4 w-4`), 20px (`h-5 w-5`), 24px (`h-6 w-6`)
- **Color:** Inherits from text color

### Common Icons Used
| Icon | Usage | Size |
|------|-------|------|
| `Mic` | Add Speaker button, recording start | h-5 w-5 |
| `MicOff` | Stop recording | h-5 w-5 |
| `Play` | Play recording button | h-5 w-5 |
| `Download` | Download recording | h-5 w-5 |
| `ArrowLeft` | Back button | h-4 w-4 |

---

## 8. Interaction Patterns

### Hover States
```
Buttons: shadow-lg with matching color
Links: text color lightening or underline
Cards/Rows: bg-secondary/40 or bg-primary/10
```

### Focus States (Accessibility)
```
Form Elements: ring-2 ring-primary/20 and border color change
```

### Active States
```
Selected Script: border-primary (yellow), bg-primary/10
Confirmed Script: border-green-500, ring-green-300, checkmark (✓)
Dragging Row: opacity-50, bg-primary/10
```

### Animations
```
Stop Recording Button: animate-pulse (built-in Tailwind)
Transitions: transition-all (smooth state changes)
```

---

## 9. Dark Mode Support

- **Strategy:** CSS Custom Properties via `:dark` pseudo-class
- **Variant:** `dark` class on html element
- **Colors:** Auto-adjust via CSS variables
- **Implementation:** Ready for future dark mode toggle

---

## 10. Accessibility

### Contrast Ratios
- Primary: Yellow on white (4.5:1+)
- Text: Foreground on background (7:1+)
- All colors meet WCAG AA standards

### ARIA Attributes
- Buttons: Proper role attributes
- Forms: Label associations
- Icons: Alt text or aria-label

### Keyboard Navigation
- All interactive elements: Tab-navigable
- Buttons: Enter/Space activation
- Form inputs: Standard behavior
- Drag/drop: Cursor indicators for mouse users

---

## 11. Performance Optimizations

### Font Loading
- **Strategy:** `display=swap` for Google Fonts
- **Result:** FOUT (Flash of Unstyled Text) is acceptable
- **Impact:** Zero render-blocking CSS

### Image Loading
- **Avatars:** 10x10px (rounded-full for speaker avatars)
- **Logo:** 32-80px depending on context
- **Lazy Loading:** Native support via `loading="lazy"`

### CSS Framework
- **Tailwind CSS v4:** Minimal, on-demand CSS generation
- **Utility Classes:** No unused styles shipped

---

## 12. API Integration Points

### Recording Upload
```
POST /api/speakers/upload-recording
Payload: { audioBlob, speakerName, scriptId }
Response: { recordingId, processedAt }
```

### Speaker Management
```
POST /api/speakers/create
PATCH /api/speakers/:id/priority
DELETE /api/speakers/:id
PATCH /api/speakers/reorder
```

See `/app/add-speaker/page.tsx` for detailed TODO comments.

---

## 13. File Structure

```
/app
  /layout.tsx              # Main layout with font imports
  /globals.css             # Global styles, Tailwind config
  /page.tsx                # Landing page
  /login                   # Authentication pages
  /signup
  /dashboard               # Main dashboard
  /add-speaker             # Speaker management page

/components
  /login-form.tsx          # Login UI component
  /speakers-list.tsx       # Dashboard speaker list
  /dashboard-navbar.tsx    # Navigation bar
  /footer.tsx              # Footer

/public
  /avatars                 # Speaker avatar animals
    /lion.png
    /owl.png
    /fox.png
    /raven.png
    /eagle.png
```

---

## 14. Accessibility & Inclusive Design

### Design Philosophy
The Canary is built with accessibility-first principles to serve users with diverse abilities, including those with:
- Speech differences or lisp
- Motor control variations
- Cognitive processing differences
- Visual impairments
- Hearing differences

### Accessibility Features

#### Wake Word Configuration Page
- **Large, centered microphone icon** (140x140px) for easy target visibility
- **Gradient visual feedback** when speaking (blue to primary yellow gradient)
- **Progress bar with 3 distinct phases** showing visual progress
- **Clear color contrasts** (WCAG AAA compliant)
- **Large touch targets** (min 44x44px for buttons)
- **Simple, uncluttered layout** reducing cognitive load

#### Font Accessibility
- Comic Relief: 16-24px for body text (never smaller than 14px)
- Manrope: 18-28px for headings (friendly, modern, readable)
- Mulish: 14-20px for secondary text (professional, clean)
- Line height: 1.5-1.6 for better readability
- Letter spacing: Generous for dyslexia-friendly reading

#### Color Accessibility
- Contrast ratios: Minimum WCAG AA (4.5:1 for small text, 3:1 for large text)
- No color-only indicators (always pair with text/icons)
- Status badges include text labels, not just colors
- Focus states: Blue ring (`ring-2 ring-primary/20`) on all interactive elements

#### Microphone Interface Specifics
- **Speaking Detection:** Visual feedback (gradient expansion) when audio detected
- **Phase Feedback:** Numbered indicators + color changes (grey → green when complete)
- **Timing:** 5-second per phrase window (not rushed)
- **Instructions:** 4 simple steps in numbered circles
- **Error Messages:** Clear, non-technical language

#### Form Inputs
- Labels always visible (not placeholder-only)
- Clear error messages with suggestions
- Required fields marked explicitly
- Input fields: minimum 44px height
- Spacing between form elements: 20px minimum

### Keyboard Navigation
- All interactive elements accessible via Tab key
- Clear focus indicators on all focusable elements
- Enter/Space key triggers buttons and links
- Escape key closes modals/dialogs
- No keyboard traps anywhere

### Screen Reader Support
- Semantic HTML tags (button, nav, main, section)
- ARIA labels on all icons (`aria-label="Settings"`)
- Form inputs have associated labels (not just placeholders)
- Skippable navigation links
- Image alt text for all meaningful images

### Motion & Animation
- Animations: max 500ms duration
- Reduced motion support: `prefers-reduced-motion: reduce` respected
- No auto-playing audio except for accessibility cues
- Transitions are smooth, not jarring

### Cognitive Load Reduction
- One primary action per screen
- Consistent layout across pages
- Clear, simple language (no jargon)
- Progress indicators for multi-step processes
- Undo functionality where possible
- Helpful tooltips without over-explaining

---

## 15. Pages & Components

### Page: Customize Wake Word (/customize-wakeword)
**Purpose:** Allow users to record and train their custom wake word phrase

**Components:**
1. Header: "Configure Your Wake Word" (Manrope, 36px)
2. Subtitle: "Speak '[word]' three times to train the system" (Mulish, 18px)
3. Microphone visualization:
   - Center icon: Mic (blue outline) or MicOff (white on gradient)
   - Ring animations: Smooth scale when speaking detected
   - Gradient: Primary yellow with shadow effect
4. Phase counter: "Recording phrase 1 of 3"
5. Progress bar: Linear progress with 3 checkpoint dots
6. Control buttons:
   - "Start Recording" (primary yellow)
   - "Stop Recording" (red, pulsing when active)
7. Instructions box: 4 numbered steps in blue/yellow palette
8. Accessibility note: Blue info box with inclusive messaging

**Layout:**
- Vertical center alignment
- Max-width: 600px
- Generous padding: 32px on sides
- Font sizes:
  - Title: 36px (Manrope, bold)
  - Subtitle: 18px (Mulish)
  - Status: 20px (Mulish, medium)
  - Instructions: 14px (Mulish)

### Component: Customize Button
- Icon: Settings (gear icon)
- Color: Primary yellow with transparent background and border
- Size: 44px height minimum
- Hover: Light yellow background fill
- Location: Manage Speakers page, next to "Add Speaker" button

### Component: Microphone Icon Ring
- Outer ring: 256px diameter, 8px border
- Inner ring: 224px diameter, 8px border (animated)
- Center circle: 160px diameter with gradient
- Speaking state: Gradient to primary, scale 1.1x, shadow
- Idle state: Light border, no shadow
- Transition: 150ms smooth

---

## 16. Summary

**The Canary** design system uses:
- **Primary Font:** Comic Relief (playful, memorable brand feel)
- **Supporting Fonts:** Manrope (professional), Mulish (friendly), Style Script (decorative)
- **Primary Color:** Yellow (#fcd34d) for energy and positivity
- **Layout:** Flexbox-first, grid for 2-column layouts
- **Spacing:** Generous padding (6-8px base unit)
- **Components:** Modular, reusable cards and buttons
- **Interactions:** Smooth transitions, clear hover states
- **Accessibility:** WCAG AA/AAA compliant, speech-diversity friendly
- **Performance:** Font optimization, lazy loading ready
- **Inclusive Design:** Purpose-built for users with speech differences, motor control variations, and diverse abilities
- **Wake Word Interface:** Large, simple, gradient-enhanced microphone with progress tracking

---

**Last Updated:** 2026-06-16
**Version:** 1.0
