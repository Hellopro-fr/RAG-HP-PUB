<template>
  <div class="wysiwyg-wrapper rounded-lg border border-gray-300 dark:border-gray-700 overflow-hidden">
    <!-- Toolbar -->
    <div v-if="editor" class="flex flex-wrap items-center gap-0.5 px-2 py-1.5 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <button
        v-for="btn in toolbarButtons"
        :key="btn.action"
        type="button"
        class="w-7 h-7 flex items-center justify-center rounded transition"
        :class="btn.isActive?.()
          ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400'
          : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'"
        :title="btn.title"
        @click="btn.command"
        v-html="btn.svg"
      />

      <div class="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />

      <!-- Link -->
      <button
        type="button"
        class="w-7 h-7 flex items-center justify-center rounded transition"
        :class="editor.isActive('link')
          ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400'
          : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'"
        title="Lien"
        @click="toggleLink"
        v-html="icons.link"
      />

      <!-- Image -->
      <button
        type="button"
        class="w-7 h-7 flex items-center justify-center rounded transition text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
        title="Image"
        @click="insertImage"
        v-html="icons.image"
      />

      <div class="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />

      <!-- Encode accents to HTML entities -->
      <button
        type="button"
        class="px-1.5 h-7 flex items-center justify-center rounded transition text-[11px] font-mono font-semibold text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
        title="Convertir les accents en entites HTML (e -> &amp;eacute;)"
        @click="encodeAccentsToEntities"
      >
        &amp;
      </button>

      <div class="w-px h-5 bg-gray-300 dark:bg-gray-600 mx-1" />

      <!-- Alignment -->
      <button
        v-for="align in alignButtons"
        :key="align.value"
        type="button"
        class="w-7 h-7 flex items-center justify-center rounded transition"
        :class="editor.isActive({ textAlign: align.value })
          ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400'
          : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'"
        :title="align.title"
        @click="editor!.chain().focus().setTextAlign(align.value).run()"
        v-html="align.svg"
      />
    </div>

    <!-- Editor content -->
    <EditorContent :editor="editor" class="wysiwyg-content" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch, computed } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import Underline from '@tiptap/extension-underline'
import TextAlign from '@tiptap/extension-text-align'
import Placeholder from '@tiptap/extension-placeholder'
import { encodeHtmlEntities } from '@/utils/htmlEntities'

const props = defineProps<{
  modelValue: string
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// SVG icons (16x16, stroke-based)
const s = (d: string) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`

const icons = {
  bold: s('<path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/><path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/>'),
  italic: s('<line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/>'),
  underline: s('<path d="M6 3v7a6 6 0 0 0 6 6 6 6 0 0 0 6-6V3"/><line x1="4" y1="21" x2="20" y2="21"/>'),
  strike: s('<line x1="4" y1="12" x2="20" y2="12"/><path d="M17.3 4.9A5.8 5.8 0 0 0 12 4c-3 0-5.3 1.8-5.3 4s2.3 4 5.3 4c3 0 5.3 1.8 5.3 4s-2.3 4-5.3 4a5.8 5.8 0 0 1-5.3-.9"/>'),
  heading: s('<path d="M6 4v16"/><path d="M18 4v16"/><path d="M6 12h12"/>'),
  bulletList: s('<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4" cy="6" r="1.5" fill="currentColor"/><circle cx="4" cy="12" r="1.5" fill="currentColor"/><circle cx="4" cy="18" r="1.5" fill="currentColor"/>'),
  orderedList: s('<line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><text x="4" y="7.5" font-size="7" fill="currentColor" stroke="none" font-family="sans-serif">1</text><text x="4" y="13.5" font-size="7" fill="currentColor" stroke="none" font-family="sans-serif">2</text><text x="4" y="19.5" font-size="7" fill="currentColor" stroke="none" font-family="sans-serif">3</text>'),
  blockquote: s('<path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4z"/>'),
  code: s('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'),
  link: s('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'),
  image: s('<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>'),
  alignLeft: s('<line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/>'),
  alignCenter: s('<line x1="18" y1="10" x2="6" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="18" y1="18" x2="6" y2="18"/>'),
  alignRight: s('<line x1="21" y1="10" x2="7" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="7" y2="18"/>'),
}

const editor = useEditor({
  content: props.modelValue,
  extensions: [
    StarterKit,
    Underline,
    Link.configure({ openOnClick: false, HTMLAttributes: { class: 'text-brand-500 underline' } }),
    Image.configure({ inline: true }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    Placeholder.configure({ placeholder: props.placeholder || 'Saisissez votre contenu...' }),
  ],
  onUpdate: ({ editor: e }) => {
    emit('update:modelValue', e.getHTML())
  },
})

watch(() => props.modelValue, (val) => {
  if (editor.value && editor.value.getHTML() !== val) {
    editor.value.commands.setContent(val, false)
  }
})

onBeforeUnmount(() => {
  editor.value?.destroy()
})

const toolbarButtons = computed(() => {
  if (!editor.value) return []
  const e = editor.value
  return [
    { action: 'bold', svg: icons.bold, title: 'Gras', command: () => e.chain().focus().toggleBold().run(), isActive: () => e.isActive('bold') },
    { action: 'italic', svg: icons.italic, title: 'Italique', command: () => e.chain().focus().toggleItalic().run(), isActive: () => e.isActive('italic') },
    { action: 'underline', svg: icons.underline, title: 'Souligne', command: () => e.chain().focus().toggleUnderline().run(), isActive: () => e.isActive('underline') },
    { action: 'strike', svg: icons.strike, title: 'Barre', command: () => e.chain().focus().toggleStrike().run(), isActive: () => e.isActive('strike') },
    { action: 'h2', svg: icons.heading, title: 'Titre', command: () => e.chain().focus().toggleHeading({ level: 2 }).run(), isActive: () => e.isActive('heading', { level: 2 }) },
    { action: 'bullet', svg: icons.bulletList, title: 'Liste', command: () => e.chain().focus().toggleBulletList().run(), isActive: () => e.isActive('bulletList') },
    { action: 'ordered', svg: icons.orderedList, title: 'Liste numerotee', command: () => e.chain().focus().toggleOrderedList().run(), isActive: () => e.isActive('orderedList') },
    { action: 'blockquote', svg: icons.blockquote, title: 'Citation', command: () => e.chain().focus().toggleBlockquote().run(), isActive: () => e.isActive('blockquote') },
    { action: 'code', svg: icons.code, title: 'Code', command: () => e.chain().focus().toggleCodeBlock().run(), isActive: () => e.isActive('codeBlock') },
  ]
})

const alignButtons = [
  { value: 'left', svg: icons.alignLeft, title: 'Aligner a gauche' },
  { value: 'center', svg: icons.alignCenter, title: 'Centrer' },
  { value: 'right', svg: icons.alignRight, title: 'Aligner a droite' },
]

function toggleLink() {
  if (!editor.value) return
  if (editor.value.isActive('link')) {
    editor.value.chain().focus().unsetLink().run()
    return
  }
  const url = window.prompt('URL du lien :')
  if (url) {
    editor.value.chain().focus().setLink({ href: url }).run()
  }
}

function insertImage() {
  if (!editor.value) return
  const url = window.prompt('URL de l\'image :')
  if (url) {
    editor.value.chain().focus().setImage({ src: url }).run()
  }
}

function encodeAccentsToEntities() {
  if (!editor.value) return
  const html = editor.value.getHTML()
  const encoded = encodeHtmlEntities(html)
  // Re-set content so the editor stays in sync; entities are decoded back to
  // chars in the display, but the emitted modelValue carries the encoded form.
  editor.value.commands.setContent(encoded, false)
  emit('update:modelValue', encoded)
}
</script>
