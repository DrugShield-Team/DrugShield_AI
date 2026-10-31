export type Message = {
  id: string;
  sender: number;
  text: string;
  time: number;
  origin?: 'starter' | 'user';
  attachment?: AttachmentReference;
  // Kept so conversations created by the image-only version still render.
  imageId?: string;
  imageName?: string;
};

export type AttachmentKind = 'image' | 'audio' | 'document';

export type AttachmentReference = {
  id: string;
  kind: AttachmentKind;
  name: string;
  mimeType: string;
  sizeBytes: number;
};

export type Conversation = {
  id: string;
  people: [string, string];
  messages: Message[];
  updatedAt: number;
  origin?: 'starter' | 'user';
};

export type PendingAttachment = AttachmentReference & { blob: Blob; previewUrl: string };

const STORAGE_KEY = 'drugshield-instagram-simulation-v1';
const STARTER_SEED_KEY = 'drugshield-instagram-starter-conversations-v1';
const MEDIA_DB = 'drugshield-instagram-simulation-media';
const MEDIA_STORE = 'images';
const viteEnvironment = (import.meta as ImportMeta & {
  env?: { VITE_DRUGSHIELD_API_URL?: string };
}).env;
const ANALYSIS_API = viteEnvironment?.VITE_DRUGSHIELD_API_URL ?? 'http://127.0.0.1:8000';

export type AnalysisSubmissionResult = {
  review_required: boolean;
  case_id: string | null;
  bot_response?: string | null;
  honeypot_link?: string | null;
  smart_bot?: {
    dispatched_message?: string;
    invoice_url?: string;
    tracking_token?: string;
    turn_count?: number;
    initial_confirmation_prompt?: string;
    delay_seconds?: number;
  } | null;
};

export async function submitMessageForAnalysis(input: {
  conversation: Conversation;
  sender: 0 | 1;
  text: string;
  attachments: PendingAttachment[];
}): Promise<AnalysisSubmissionResult> {
  const [senderName, recipientName] = input.sender === 0
    ? [input.conversation.people[0], input.conversation.people[1]]
    : [input.conversation.people[1], input.conversation.people[0]];
  const isAnalyst = input.sender === 1;
  const event = {
    schema_version: 1,
    channel: 'instagram',
    message_id: crypto.randomUUID(),
    conversation_id: input.conversation.id,
    sender_id: isAnalyst ? `analyst:${input.conversation.id}` : `participant:${input.conversation.id}`,
    sender_display_name: senderName,
    recipient_id: isAnalyst ? `participant:${input.conversation.id}` : `analyst:${input.conversation.id}`,
    recipient_display_name: recipientName,
    timestamp: new Date().toISOString(),
    text: input.text.trim(),
  };
  const body = new FormData();
  body.append('event_json', JSON.stringify(event));
  input.attachments.forEach((attachment) => {
    body.append('files', attachment.blob, attachment.name);
  });
  const response = await fetch(`${ANALYSIS_API}/api/v1/simulation-events`, {
    method: 'POST',
    body,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail?.error ?? error?.detail ?? `Analysis API returned HTTP ${response.status}`);
  }
  return response.json();
}

export function createStarterConversations(): Conversation[] {
  const now = Date.now();
  const starterMessage = (id: string, sender: number, text: string, minutesAgo: number): Message => ({
    id,
    sender,
    text,
    time: now - minutesAgo * 60_000,
    origin: 'starter',
  });

  return [
    {
      id: 'starter-aarav-malik',
      origin: 'starter',
      people: ['Aarav Malik', 'You'],
      messages: [
        starterMessage('starter-aarav-1', 0, 'I have cannabis for sale. Are you still interested?', 18),
        starterMessage('starter-aarav-2', 1, 'No. I do not want to buy illegal drugs.', 16),
        starterMessage('starter-aarav-3', 0, 'I can also get unprescribed pills.', 14),
      ],
      updatedAt: now - 14 * 60_000,
    },
    {
      id: 'starter-sana-qureshi',
      origin: 'starter',
      people: ['Sana Qureshi', 'You'],
      messages: [
        starterMessage('starter-sana-1', 0, 'Are you looking for prescription pills without a prescription?', 45),
        starterMessage('starter-sana-2', 1, 'No. Please stop offering me illegal drugs.', 42),
        starterMessage('starter-sana-3', 0, 'I am a dealer and can supply more later.', 39),
      ],
      updatedAt: now - 39 * 60_000,
    },
    {
      id: 'starter-kabir-sethi',
      origin: 'starter',
      people: ['Kabir Sethi', 'You'],
      messages: [
        starterMessage('starter-kabir-1', 0, 'I have MDMA available for sale.', 95),
        starterMessage('starter-kabir-2', 1, 'I am not interested. This is illegal.', 92),
        starterMessage('starter-kabir-3', 0, 'I can connect you with another supplier.', 88),
      ],
      updatedAt: now - 88 * 60_000,
    },
  ];
}


export function clearLocalData(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STARTER_SEED_KEY);
    localStorage.removeItem('drugshield-instagram-simulation-theme');
    indexedDB.deleteDatabase(MEDIA_DB);
  } catch {}
}

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const saved: unknown = JSON.parse(raw ?? '[]');
    if (!Array.isArray(saved)) return [];
    if (localStorage.getItem(STARTER_SEED_KEY) === '1') return saved as Conversation[];

    const starters = createStarterConversations();
    const savedIds = new Set((saved as Conversation[]).map((conversation) => conversation.id));
    const conversations = [...starters.filter((conversation) => !savedIds.has(conversation.id)), ...(saved as Conversation[])]
      .sort((a, b) => b.updatedAt - a.updatedAt);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
      localStorage.setItem(STARTER_SEED_KEY, '1');
    } catch { /* Keep the starter inbox usable for this session if browser storage is full. */ }
    return conversations;
  } catch { /* Use an empty inbox if browser storage is unavailable or invalid. */ }
  return [];
}

export function saveConversations(conversations: Conversation[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
}

export function createConversation(people: [string, string]): Conversation {
  return { id: crypto.randomUUID(), people, messages: [], updatedAt: Date.now(), origin: 'user' };
}

function openMediaDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(MEDIA_DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(MEDIA_STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('Could not open local attachment storage.'));
  });
}

async function saveAttachmentLocally(id: string, blob: Blob): Promise<void> {
  const db = await openMediaDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(MEDIA_STORE, 'readwrite');
    transaction.objectStore(MEDIA_STORE).put(blob, id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error('Could not save this attachment.'));
    transaction.onabort = () => reject(transaction.error ?? new Error('Could not save this attachment.'));
  }).finally(() => db.close());
}

export async function loadStoredAttachment(id: string): Promise<Blob | undefined> {
  const db = await openMediaDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(MEDIA_STORE, 'readonly');
    const request = transaction.objectStore(MEDIA_STORE).get(id);
    request.onsuccess = () => resolve(request.result as Blob | undefined);
    request.onerror = () => reject(request.error ?? new Error('Could not read this attachment.'));
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => { db.close(); reject(transaction.error); };
  });
}

export async function deleteStoredAttachments(ids: string[]): Promise<void> {
  await Promise.all(ids.map(async (id) => {
    const db = await openMediaDatabase();
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(MEDIA_STORE, 'readwrite');
      transaction.objectStore(MEDIA_STORE).delete(id);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error('Could not remove a saved attachment.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Could not remove a saved attachment.'));
    }).finally(() => db.close());
  }));
}

async function compressImage(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext('2d');
  if (!context) { bitmap.close(); throw new Error('This image could not be prepared.'); }
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.82));
  if (!blob) throw new Error('This image could not be prepared.');
  return blob;
}

export async function prepareAttachment(file: File, kind: AttachmentKind): Promise<PendingAttachment> {
  const blob = kind === 'image' ? await compressImage(file) : file;
  return {
    id: crypto.randomUUID(),
    kind,
    name: file.name,
    mimeType: blob.type || file.type || 'application/octet-stream',
    sizeBytes: blob.size,
    blob,
    previewUrl: URL.createObjectURL(blob),
  };
}

export async function sendMessage(input: {
  conversationId: string;
  sender: number;
  text: string;
  attachments: PendingAttachment[];
}): Promise<Message[]> {
  const now = Date.now();
  const messages: Message[] = [];
  if (input.text.trim()) {
    messages.push({ id: crypto.randomUUID(), sender: input.sender, text: input.text.trim(), time: now, origin: 'user' });
  }

  for (const attachment of input.attachments) {
    await saveAttachmentLocally(attachment.id, attachment.blob);
    messages.push({
      id: crypto.randomUUID(),
      sender: input.sender,
      text: '',
      origin: 'user',
      attachment: {
        id: attachment.id,
        kind: attachment.kind,
        name: attachment.name,
        mimeType: attachment.mimeType,
        sizeBytes: attachment.sizeBytes,
      },
      ...(attachment.kind === 'image' ? { imageId: attachment.id, imageName: attachment.name } : {}),
      time: now,
    });
  }

  return messages;
}

export function appendMessagesToConversation(
  conversations: Conversation[],
  conversationId: string,
  messages: Message[],
): Conversation[] {
  const lastMessage = messages[messages.length - 1];
  if (!lastMessage) return conversations;
  return conversations.map((conversation) => conversation.id === conversationId
    ? { ...conversation, messages: [...conversation.messages, ...messages], updatedAt: lastMessage.time }
    : conversation).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function removeConversation(conversations: Conversation[], conversationId: string): {
  remaining: Conversation[];
  removedAttachmentIds: string[];
} {
  const removed = conversations.find((conversation) => conversation.id === conversationId);
  if (!removed) return { remaining: conversations, removedAttachmentIds: [] };

  const remaining = conversations.filter((conversation) => conversation.id !== conversationId);
  const attachmentId = (message: Message) => message.attachment?.id ?? message.imageId;
  const retainedAttachmentIds = new Set(remaining.flatMap((conversation) => conversation.messages.flatMap((message) => {
    const id = attachmentId(message);
    return id ? [id] : [];
  })));
  const removedAttachmentIds = removed.messages.flatMap((message) => {
    const id = attachmentId(message);
    return id && !retainedAttachmentIds.has(id) ? [id] : [];
  });
  return { remaining, removedAttachmentIds };
}
