'use client';

import { useState, useTransition, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Trash2, Plus, GripVertical } from 'lucide-react';
import {
  getSpeakers,
  refreshSpeakers,
  setSpeakers,
  changePriority as changePriorityInStore,
  deleteSpeaker as deleteSpeakerInStore,
} from '@/lib/speakers-store';
import type { Speaker } from '@/lib/speakers-store';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// Sortable item component
function SortableSpeakerRow({ speaker, onPriorityChange, onDelete }: any) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: speaker.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="grid grid-cols-12 gap-4 p-4 hover:bg-secondary/30 transition-colors items-center"
    >
      {/* Drag Handle */}
      <div
        className="col-span-1 cursor-grab active:cursor-grabbing flex items-center justify-center"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4 text-muted-foreground" />
      </div>

      {/* Icon */}
      <div className="col-span-1 text-3xl">{speaker.icon}</div>

      {/* Name */}
      <div className="col-span-3">
        <p className="font-semibold text-foreground">{speaker.name}</p>
      </div>

      {/* Priority Dropdown */}
      <div className="col-span-2">
        <select
          value={speaker.priority}
          onChange={(e) => onPriorityChange(speaker.id, parseInt(e.target.value))}
          className="w-full px-3 py-2 rounded-lg border border-border bg-card text-sm font-bold cursor-pointer hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          {[5, 4, 3, 2, 1].map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      {/* Delete Button */}
      <div className="col-span-5 flex justify-end">
        <button
          onClick={() => onDelete(speaker.id)}
          className="inline-flex items-center justify-center rounded-lg border border-red-300 p-2 text-red-600 hover:bg-red-50 transition-colors"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export default function ManageSpeakersPage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [speakers, setSpeakersState] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Load speakers on mount and sync updates
  useEffect(() => {
    let alive = true;
    const cached = getSpeakers();
    if (cached.length) setSpeakersState(cached);

    refreshSpeakers()
      .then((fresh) => {
        if (alive) setSpeakersState(fresh);
      })
      .catch((e) => console.error('refresh failed', e))
      .finally(() => {
        if (alive) setLoading(false);
      });

    const handleStorageChange = () => {
      if (alive) setSpeakersState(getSpeakers());
    };
    window.addEventListener('storage', handleStorageChange);
    return () => {
      alive = false;
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  // Get normal speakers (non-accessibility) sorted by priority
  const normalSpeakers = speakers.filter(s => !s.isAccessible).sort((a, b) => b.priority - a.priority);
  const accessibilitySpeaker = speakers.find(s => s.isAccessible);

  // Handle drag end
  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = normalSpeakers.findIndex(s => s.id === active.id);
      const newIndex = normalSpeakers.findIndex(s => s.id === over.id);
      const newOrder = arrayMove(normalSpeakers, oldIndex, newIndex);
      
      // Assign priorities based on new order (top = highest)
      const updated = speakers.map(s => {
        if (s.isAccessible) return s;
        const orderIndex = newOrder.findIndex(ns => ns.id === s.id);
        return { ...s, priority: newOrder.length - orderIndex };
      });

      // Optimistic UI update
      setSpeakersState(updated);
      setSpeakers(updated);

      // Persist each changed priority to backend
      try {
        await Promise.all(
          updated
            .filter(s => !s.isAccessible)
            .map(s => changePriorityInStore(s.id, s.priority))
        );
      } catch (err) {
        console.error('Drag priority update failed:', err);
      }
    }
  };

  const handlePriorityChange = async (speakerId: string, newPriority: number) => {
    try {
      await changePriorityInStore(speakerId, newPriority);
      setSpeakersState(getSpeakers());
    } catch (err) {
      console.error('Priority update failed:', err);
      alert('Failed to update priority.');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSpeakerInStore(id);
      setSpeakersState(getSpeakers());
    } catch (err) {
      console.error('Delete failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to delete speaker.');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-6 flex items-center justify-center">
        <p className="text-muted-foreground">Loading speakers...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Manage Speakers</h1>
            <p className="mt-2 text-muted-foreground">Organize speaker priority</p>
          </div>
          <button
            onClick={() => startTransition(() => router.push('/dashboard'))}
            disabled={isPending}
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary disabled:opacity-60"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
        </div>

        {/* Speakers Table - includes both normal and accessibility */}
        <div className="mb-8 rounded-lg border border-border bg-card overflow-hidden">
          {/* Table Header */}
          <div className="grid grid-cols-12 gap-4 p-4 bg-secondary/50 border-b border-border font-semibold text-foreground text-sm">
            <div className="col-span-1">Drag</div>
            <div className="col-span-1">Icon</div>
            <div className="col-span-3">Name</div>
            <div className="col-span-2">Priority</div>
            <div className="col-span-5"></div>
          </div>

          {/* Table Rows with Drag Context */}
          <div className="divide-y divide-border">
            {normalSpeakers.length === 0 && !accessibilitySpeaker ? (
              <div className="p-8 text-center text-muted-foreground">
                No speakers added yet
              </div>
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={normalSpeakers.map(s => s.id)}
                  strategy={verticalListSortingStrategy}
                >
                  {/* Normal Speakers - Draggable */}
                  {normalSpeakers.map((speaker) => (
                    <SortableSpeakerRow
                      key={speaker.id}
                      speaker={speaker}
                      onPriorityChange={handlePriorityChange}
                      onDelete={handleDelete}
                    />
                  ))}
                </SortableContext>

                {/* Separator for accessibility speaker */}
                {accessibilitySpeaker && normalSpeakers.length > 0 && (
                  <div className="h-2 bg-gray-100 dark:bg-gray-800"></div>
                )}

                {/* Accessibility Speaker - as last row (not draggable) */}
                {accessibilitySpeaker && (
                  <div className="grid grid-cols-12 gap-4 p-4 hover:bg-blue-50/30 dark:hover:bg-blue-950/20 transition-colors items-center bg-blue-50/10 dark:bg-blue-950/5">
                    {/* Empty space for drag handle */}
                    <div className="col-span-1"></div>

                    {/* Icon - Red Plus Sign */}
                    <div className="col-span-1 flex items-center justify-center text-2xl font-bold text-red-600">
                      +
                    </div>

                    {/* Name */}
                    <div className="col-span-3">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-foreground">{accessibilitySpeaker.name}</p>
                        <span className="inline-block px-2 py-1 text-xs font-semibold bg-blue-200 text-blue-800 dark:bg-blue-900 dark:text-blue-100 rounded">
                          Special
                        </span>
                      </div>
                    </div>

                    {/* No Priority */}
                    <div className="col-span-2">
                      <p className="text-sm text-muted-foreground font-medium">—</p>
                    </div>

                    {/* Delete Button */}
                    <div className="col-span-5 flex justify-end">
                      <button
                        onClick={() => handleDelete(accessibilitySpeaker.id)}
                        className="inline-flex items-center justify-center rounded-lg border border-red-300 p-2 text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )}
              </DndContext>
            )}
          </div>
        </div>

        {/* Add Speaker Button */}
        <div className="flex justify-end">
          <button
            onClick={() => startTransition(() => router.push('/add-speaker'))}
            disabled={isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-semibold text-primary-foreground transition-all hover:shadow-lg disabled:opacity-60"
          >
            <Plus className="h-5 w-5" />
            Add New Speaker
          </button>
        </div>
      </div>
    </div>
  );
}
