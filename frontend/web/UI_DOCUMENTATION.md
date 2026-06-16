# Voice Assistant UI Documentation

This document provides a comprehensive overview of all user interface screens and features in the Voice Assistant application.

## Overview

The Voice Assistant application is a voice training and management system that allows users to:
- Record voice samples for multiple speakers/assistants
- Manage speaker priorities and settings
- View dashboard with active speakers
- Add new speakers with customized voice training

---

## 1. Dashboard Page (`/dashboard`)

**Purpose**: Main hub showing all active voice assistants and their status

### Key Features:
- **Speaker Cards**: Displays all speakers in a card-based layout
- **Priority Display**: Shows speaker priority (1-5) for normal speakers
- **Status Badges**: Indicates current status (Active, Scheduled, Completed)
- **Advanced Listener Section**: Special accessibility-enabled speaker shown separately without priority
  - Marked with "Accessibility enabled" label
  - Highlighted with blue styling to differentiate from normal speakers
  - Red plus (+) icon indicator

### Layout:
- Header: "Manage and monitor voice assistants" title
- Speaker cards arranged vertically
- Each card shows: Icon, Name, Priority, Status
- Advanced Listener card at bottom with special styling

### Navigation:
- "Manage Speakers" button: Navigate to speaker management
- Access via dashboard header

---

## 2. Manage Speakers Page (`/manage-speakers`)

**Purpose**: Central hub for organizing speakers, adjusting priorities, and managing entries

### Key Features:

#### Drag-and-Drop Reordering
- **Drag Handle**: Grip icon on the left of each speaker row
- **Functionality**: Click and drag speakers to reorder them
- **Auto-update**: Priorities automatically adjust based on drag order
- **Visual Feedback**: Row opacity changes during drag, cursor changes to grab/grabbing

#### Speaker Table
- **Columns**: Drag Handle | Icon | Name | Priority | Actions
- **Normal Speakers** (Sorted by priority, highest first):
  - Canary Assistant (Priority 4)
  - Canary Neural (Priority 2)
  - Voice Model Pro (Priority 1)
  - Smart Engine (Priority 1)
  - Echo Voice (Priority 1)

#### Advanced Listener Row
- **Icon**: Red Plus Sign (+)
- **Status**: Marked with "Special" badge (blue)
- **Priority**: Shows "—" (dash) - no priority value
- **Background**: Light blue tint to distinguish from normal speakers

#### Priority Management
- **Dropdown Selector**: Change speaker priority via dropdown (1-5)
- **Duplicate Allowed**: Multiple speakers can have the same priority
- **Persistent**: Changes save immediately to sessionStorage

#### Speaker Actions
- **Delete Button**: Red trash icon button on the right
- **Visual Feedback**: Button shows red border, hover effect with light red background

### Layout:
- Header with "Manage Speakers" title and "Back" button
- Table header with column labels
- Draggable speaker rows
- Accessibility speaker separator line
- Advanced Listener special row
- "Add New Speaker" button (bottom right, yellow/primary color)

### Navigation:
- "Back" button: Return to dashboard
- "Add New Speaker" button: Navigate to add-speaker page

---

## 3. Add Speaker Page (`/add-speaker`)

**Purpose**: Multi-step form to register new voice assistants with voice samples

### Form Sections:

#### Speaker Information (Left Column)
**Fields:**
- **Name**: Text input for speaker/assistant name
- **City**: Speaker's city location
- **Country**: Speaker's country
- **Music Genre**: Dropdown selection for preferred music genre (Jazz, Classical, etc.)
- **Speaker Priority**: Dropdown (1-5) - **Hidden when accessibility is enabled**

#### Voice Type Selection (Right Column)
**Option 1: Standard Voice Recording**
- Label: "For people without speech differences"
- Default option
- Triggers script-based recording flow (3 scripts)

**Option 2: Accessibility Mode**
- Label: "For people with speech differences or challenges"
- When checked:
  - Hides priority selection field
  - Changes recording to question-based format (3 questions instead of scripts)
  - Allows only one accessibility speaker at a time

### Recording Section (Below Form)

#### Standard Recording Flow (3 Scripts)
**Scripts to Record:**
1. **Script 1 — Natural Speech**: "Speak clearly and naturally at your normal pace."
2. **Script 2 — Varied Pace**: "Start a little faster, then slow down — vary your rhythm."
3. **Script 3 — Questions & Commands**: "Use natural question and command intonation."

**Recording Interface per Script:**
- Script title and description
- Red "Start Recording" button
- Recording timer
- Audio playback control (Play Recording)
- Delete recorded audio button

#### Accessibility Recording Flow (3 Questions)
**Questions to Record:**
1. "How was your day today?"
2. "What have you been working on?"
3. "What's your favorite memory?"

**Recording Interface:**
- "Question X of 3" indicator
- Question text displayed in panel
- Red "Record Answer" button
- Recording timer
- Navigation: "Previous" and "Next Question" buttons
- Completion indicator: "✓ All recordings complete"

### Recording Status Indicators
- **Checked Checkmarks** (✓): Green checkmark when script/question recorded
- **Empty Circles**: Gray circle when not yet recorded
- **Completion Message**: Green banner showing "✓ All recordings complete"

### Form Submission

#### When All Scripts Complete:
- If fewer than 5 normal speakers:
  - Shows "Confirm Add Voice" modal
  - Allows review before final submission
  
- If 5 speakers already exist:
  - Shows "Speaker Limit Reached" modal
  - Lists all current normal speakers
  - User selects which speaker to remove
  - Proceeds with adding new speaker (replacing selected one)

#### When All Questions Complete (Accessibility):
- If accessibility speaker exists:
  - Shows "Accessibility Voice Limit" modal
  - Lists existing accessibility speaker
  - User must select to replace it
  - Only one accessibility speaker allowed
  
- If no accessibility speaker exists:
  - Directly adds speaker without confirmation

### Layout:
- Header with "Back" button
- Two-column form layout on desktop
- Form section with speaker details (left)
- Voice type selection (right)
- Recording section (full width, below form)
- Form buttons at bottom (Cancel / Confirm)

### Colors & Styling:
- **Record Buttons**: Yellow/Primary background
- **Cancel Buttons**: Border only, secondary style
- **Recording Indicators**: Green for completed, gray for pending
- **Delete/Remove**: Red styling

---

## 4. Modal Dialogs

### Speaker Limit Reached Modal
**Triggered**: When adding normal speaker and 5 already exist

**Content:**
- Title: "Speaker Limit Reached"
- Message: "You have reached the maximum of 5 healthy speakers. Which speaker would you like to remove to add this new one?"
- **Speaker List**: 
  - Displays all 5 current speakers
  - Each item shows: Speaker name + Priority
  - Click to select (highlighted with blue border when selected)
- **Buttons**: Cancel | Remove & Add New

### Accessibility Voice Limit Modal
**Triggered**: When adding accessibility speaker and one already exists

**Content:**
- Title: "Accessibility Voice Limit"
- Message: "Only one accessibility-enabled speaker is allowed. Which existing speaker would you like to replace?"
- **Speaker List**: Shows existing accessibility speaker
- **Buttons**: Cancel | Replace & Continue

---

## 5. Design System

### Colors
- **Primary**: Used for buttons, active states, accents
- **Red/Danger**: Delete actions, error states, red plus icon
- **Blue**: Accessibility indicators, "Special" badges, status badges
- **Gray/Muted**: Neutral text, disabled states, borders
- **Green**: Success states, completion checkmarks

### Typography
- **Headings**: Bold, larger sizes for page titles
- **Labels**: Semi-bold, medium size for form labels
- **Body**: Regular weight for descriptions and body text
- **Emphasis**: Semi-bold or font colors for priority numbers

### Icons
- **Speaker Icons**: Emoji representations (animals: owl, fox, lion, eagle, horse, wolf)
- **Advanced Listener Icon**: Red plus sign (+)
- **Actions**: Trash icon for delete, grip icon for drag, plus icon for add
- **Status**: Checkmark for completed, circle for pending

### Spacing
- **Cards/Containers**: 6-8 units padding
- **Gaps**: 4 units between elements
- **Sections**: 8 units vertical spacing

---

## 6. Key Workflows

### Workflow 1: Add a New Speaker (Normal)
1. Navigate to "Add Speaker" from dashboard or manage speakers
2. Fill speaker information (name, city, country, music genre)
3. Select "Standard Voice Recording" option
4. Record Script 1 — click "Start Recording", speak naturally, save
5. Record Script 2 — click "Start Recording", vary pace, save
6. Record Script 3 — click "Start Recording", use command intonation, save
7. When all 3 scripts recorded:
   - If <5 speakers exist: See "Confirm Add Voice" modal, click "Confirm"
   - If 5 speakers exist: See "Speaker Limit Reached" modal, select speaker to remove, click "Remove & Add New"
8. Redirects to dashboard showing new speaker

### Workflow 2: Add Accessibility Speaker
1. Navigate to "Add Speaker"
2. Check "For people with speech differences" checkbox
   - Priority field disappears automatically
3. Fill speaker name only (city, country, genre optional)
4. Select "Accessibility" option (auto-selected when checkbox enabled)
5. Record Answer for Question 1, 2, 3
6. When all 3 answers recorded:
   - If no existing accessibility speaker: Directly added
   - If one exists: Shows modal to confirm replacement
7. Redirects to dashboard

### Workflow 3: Manage Speaker Priority
1. Go to "Manage Speakers"
2. **Via Dropdown**: Select new priority from dropdown (1-5) - changes instantly
3. **Via Drag-and-Drop**: Click grip icon, drag speaker to new position - priority auto-adjusts
4. Changes persist to sessionStorage

### Workflow 4: Delete a Speaker
1. Go to "Manage Speakers"
2. Click red trash icon on speaker's row
3. Speaker removed immediately from list
4. Priorities adjust if needed

---

## 7. Data Structure

### Speaker Object
```typescript
{
  id: string;                 // Unique identifier
  name: string;              // Speaker name
  icon: string;              // Emoji icon representation
  priority: number;          // 0 (accessibility) or 1-5 (normal)
  isAccessible: boolean;     // True for accessibility mode
}
```

### Storage
- **Method**: sessionStorage
- **Key**: `speakers_db`
- **Format**: JSON array of Speaker objects
- **Persistence**: Cleared on browser session end

---

## 8. Accessibility Features

### Advanced Listener (Accessibility Speaker)
- **Purpose**: Designed for users with speech differences or challenges
- **Differences**:
  - Questions instead of scripts
  - No priority management (shown as "—")
  - Separate row with blue highlighting
  - Special badge indicator
  - Red plus icon to differentiate
- **Limitation**: Only one allowed at a time
- **Dashboard**: Shown separately from normal speakers

---

## 9. Error Handling & Edge Cases

### Edge Case 1: Form Incomplete
- **If**: User tries to submit without completing all scripts/questions
- **Result**: Alert message appears asking to complete recordings

### Edge Case 2: 5 Normal Speakers Exist
- **If**: User tries to add 6th normal speaker
- **Result**: Modal forces selection of speaker to remove before adding new one

### Edge Case 3: Duplicate Priorities
- **If**: Multiple speakers set to same priority (e.g., two speakers with priority 1)
- **Behavior**: Allowed and maintained - no auto-adjustment
- **Display**: All priorities shown as selected in table

### Edge Case 4: Accessibility Speaker Already Exists
- **If**: User tries to add new accessibility speaker when one exists
- **Result**: Modal shows existing speaker, requires confirmation to replace

---

## 10. Browser Compatibility & Requirements

- **Modern Browsers**: Chrome, Firefox, Safari, Edge
- **JavaScript**: Required (Next.js/React application)
- **Storage**: sessionStorage (5-10MB typical)
- **Audio API**: Web Audio API for recording functionality
- **Screen Size**: Optimized for desktop (may need responsive improvements for mobile)

---

## Summary Table: All UI Pages

| Page | URL | Purpose | Key Features |
|------|-----|---------|--------------|
| Dashboard | `/dashboard` | View all speakers | Cards, priority display, speaker status |
| Manage Speakers | `/manage-speakers` | Organize speakers | Drag-drop, priority dropdown, delete |
| Add Speaker | `/add-speaker` | Register new speaker | Forms, recording, modal submission |
| Modal | (Overlay) | Confirm/limit speakers | Speaker selection, confirmation |

---

**Last Updated**: Current Version
**Status**: Fully Documented
**Features**: All UI screens documented with full descriptions and workflows
