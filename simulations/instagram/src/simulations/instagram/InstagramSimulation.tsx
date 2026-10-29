import { FormEvent, KeyboardEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import EmojiPicker from 'emoji-picker-react';
import './instagram-simulation.css';
import {
  appendMessagesToConversation,
  createConversation as createLocalConversation,
  deleteStoredAttachments,
  loadConversations,
  loadStoredAttachment,
  prepareAttachment,
  removeConversation,
  saveConversations,
  submitMessageForAnalysis,
  sendMessage as sendLocalMessage,
  type AttachmentKind,
  type AttachmentReference,
  type AnalysisSubmissionResult,
  type Conversation,
  type Message,
  type PendingAttachment,
} from './messageService';

const THEME_KEY = 'drugshield-instagram-simulation-theme';
const STORY_PROFILES = [
  { username: 'violet.rx', art: 'capsule', symbol: '💊', caption: 'A colorful capsule illustration' },
  { username: 'night.chemist', art: 'flask', symbol: '⚗️', caption: 'A fictional glass flask illustration' },
  { username: 'cloud.packet', art: 'crystal', symbol: '💎', caption: 'A fictional crystal illustration' },
  { username: 'syrupwave', art: 'bottle', symbol: '🧴', caption: 'A fictional bottle illustration' },
] as const;

function readTheme(): 'light' | 'dark' {
  try { return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'; } catch { return 'light'; }
}

function Icon({ name, size = 24 }: { name: string; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true as const };
  const paths: Record<string, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v12h14V9M9 21v-7h6v7"/></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></>,
    explore: <><rect x="3" y="3" width="18" height="18" rx="5"/><path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8z"/></>,
    reels: <><rect x="3" y="3" width="18" height="18" rx="5"/><path d="m10 8 6 4-6 4zM4 8h16M8 4l3 4m3-4 3 4"/></>,
    instagram: <><defs><linearGradient id="instagram-gradient" x1="4" y1="20" x2="20" y2="4" gradientUnits="userSpaceOnUse"><stop stopColor="#feda75"/><stop offset=".45" stopColor="#fa7e1e"/><stop offset=".72" stopColor="#d62976"/><stop offset="1" stopColor="#4f5bd5"/></linearGradient></defs><rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5.2" stroke="url(#instagram-gradient)" strokeWidth="2.1"/><circle cx="12" cy="12" r="4.1" stroke="url(#instagram-gradient)" strokeWidth="2.1"/><circle cx="17.7" cy="6.7" r="1.15" fill="#d62976" stroke="none"/></>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></>,
    moon: <path d="M20.8 13.1A8.5 8.5 0 0 1 10.9 3.2 8.5 8.5 0 1 0 20.8 13.1Z"/>,
    heart: <path d="M20.8 8.8c0 5.2-8.8 10-8.8 10s-8.8-4.8-8.8-10a4.5 4.5 0 0 1 8.8-1.5 4.5 4.5 0 0 1 8.8 1.5Z"/>,
    message: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></>,
    create: <><rect x="3" y="3" width="18" height="18" rx="5"/><path d="M12 8v8m-4-4h8"/></>,
    menu: <><path d="M4 6h16M4 12h16M4 18h16"/></>,
    more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
    video: <><rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3"/></>,
    phone: <path d="M21 16.5v3a2 2 0 0 1-2.2 2A19.8 19.8 0 0 1 10.2 18a19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 1.9 3.2 2 2 0 0 1 3.9 1h3a2 2 0 0 1 2 1.7l.5 3a2 2 0 0 1-.6 1.7L7.5 8.7a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 1.7-.6l3 .5a2 2 0 0 1 1.5 2.2Z"/>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></>,
    attachment: <path d="m21.4 11.1-8.5 8.5a5.5 5.5 0 0 1-7.8-7.8l9.2-9.2a3.7 3.7 0 0 1 5.2 5.2l-9.2 9.2a1.8 1.8 0 0 1-2.6-2.6l8.5-8.5"/>,
    mic: <><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8"/></>,
    smile: <><circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/></>,
    send: <><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></>,
    close: <><path d="m18 6-12 12M6 6l12 12"/></>,
  };
  return <svg {...common}>{paths[name] ?? paths.message}</svg>;
}

function Avatar({ name, size = 'regular' }: { name: string; size?: 'small' | 'regular' | 'large' }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || '?';
  return <span className={`avatar avatar--${size}`} role="img" aria-label={name}>{initials}</span>;
}

function formatTime(timestamp: number) {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(timestamp);
}

function getMessageAttachment(message: Message): AttachmentReference | null {
  if (message.attachment) return message.attachment;
  return message.imageId ? {
    id: message.imageId,
    kind: 'image',
    name: message.imageName ?? 'Attached image',
    mimeType: 'image/jpeg',
    sizeBytes: 0,
  } : null;
}

function formatFileSize(bytes: number) {
  if (!bytes) return '';
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderMessageText(text: string) {
  if (!text) return '';
  const urlPattern = /(https?:\/\/[^\s<]+)/g;
  const parts = text.split(urlPattern);
  return parts.map((part, i) => {
    if (part.match(urlPattern)) {
      return (
        <a
          key={i}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#53bdeb', textDecoration: 'underline', wordBreak: 'break-all', fontWeight: 500 }}
        >
          {part}
        </a>
      );
    }
    return part;
  });
}

export default function InstagramSimulation() {
  const [theme, setTheme] = useState<'light' | 'dark'>(readTheme);
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [speaker, setSpeaker] = useState<0 | 1>(0);
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [secondName, setSecondName] = useState('');
  const [mobileShowChat, setMobileShowChat] = useState(false);
  const [openConversationMenu, setOpenConversationMenu] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<Conversation | null>(null);
  const [activeStory, setActiveStory] = useState<(typeof STORY_PROFILES)[number] | null>(null);
  const [notice, setNotice] = useState('');
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [attachmentSources, setAttachmentSources] = useState<Record<string, string>>({});
  const messageEnd = useRef<HTMLDivElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const attachmentInput = useRef<HTMLInputElement>(null);
  const audioInput = useRef<HTMLInputElement>(null);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const pendingAttachmentsRef = useRef(pendingAttachments);
  const attachmentSourcesRef = useRef(attachmentSources);
  pendingAttachmentsRef.current = pendingAttachments;
  attachmentSourcesRef.current = attachmentSources;
  const active = conversations.find((conversation) => conversation.id === activeId) ?? null;
  const filteredConversations = useMemo(() => conversations.filter((conversation) =>
    conversation.people.some((name) => name.toLowerCase().includes(search.toLowerCase()))), [conversations, search]);

  useEffect(() => {
    try { saveConversations(conversations); } catch { setNotice('Browser storage is unavailable; changes will not persist after closing this page.'); }
  }, [conversations]);
  useEffect(() => {
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* Theme still works for this session. */ }
  }, [theme]);
  useEffect(() => {
    let cancelled = false;
    const attachmentIds = [...new Set(conversations.flatMap((conversation) => conversation.messages.flatMap((message) => {
      const id = message.attachment?.id ?? message.imageId;
      return id ? [id] : [];
    })))];
    Promise.all(attachmentIds.map(async (id) => {
      if (attachmentSourcesRef.current[id]) return [id, attachmentSourcesRef.current[id]] as const;
      const blob = await loadStoredAttachment(id);
      return blob ? [id, URL.createObjectURL(blob)] as const : null;
    })).then((entries) => {
      if (!cancelled) setAttachmentSources((current) => ({ ...current, ...Object.fromEntries(entries.filter((entry): entry is readonly [string, string] => entry !== null)) }));
    }).catch(() => { if (!cancelled && attachmentIds.length) setNotice('Some saved attachments could not be loaded from this browser.'); });
    return () => { cancelled = true; };
  }, [conversations]);
  useEffect(() => () => {
    pendingAttachmentsRef.current.forEach((attachment) => URL.revokeObjectURL(attachment.previewUrl));
    Object.values(attachmentSourcesRef.current).forEach((url) => URL.revokeObjectURL(url));
  }, []);
  useEffect(() => { messageEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [active?.messages.length, activeId]);

  function createConversation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const people: [string, string] = [firstName.trim(), secondName.trim()];
    if (!people[0] || !people[1]) return;
    const conversation = createLocalConversation(people);
    setConversations((current) => [conversation, ...current]);
    setActiveId(conversation.id);
    setSpeaker(0);
    setMobileShowChat(true);
    setModalOpen(false);
    setFirstName('');
    setSecondName('');
    setNotice(`Conversation with ${people[0]} and ${people[1]} created.`);
  }

  async function sendMessage(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!active || (!draft.trim() && pendingAttachments.length === 0)) return;
    const currentSpeaker = speaker;
    const currentActiveId = active.id;
    let result: AnalysisSubmissionResult;
    try {
      result = await submitMessageForAnalysis({
        conversation: active,
        sender: currentSpeaker,
        text: draft,
        attachments: pendingAttachments,
      });
    } catch (error) {
      setNotice(error instanceof Error ? `Message not sent: ${error.message}` : 'Message not sent because the analysis service is unavailable.');
      return;
    }
    try {
      const messages = await sendLocalMessage({ conversationId: active.id, sender: currentSpeaker, text: draft, attachments: pendingAttachments });
      setConversations((current) => appendMessagesToConversation(current, active.id, messages));
      setAttachmentSources((current) => ({ ...current, ...Object.fromEntries(pendingAttachments.map((attachment) => [attachment.id, attachment.previewUrl])) }));
      if (result.review_required) setNotice(`Message analyzed and sent for human review${result.case_id ? ` (case ${result.case_id.slice(0, 8)})` : ''}.`);
      else setNotice('Message analyzed by the backend.');
    } catch {
      setNotice('Could not save the attachment in this browser. Check available storage and try a smaller file.');
      return;
    }
    setDraft('');
    setPendingAttachments([]);

    // 1. Auto-shift sender:
    // If dealer (0) sent a message, automatically toggle to Undercover Buyer (1) for next turn
    // If buyer (1) sent a message, automatically toggle back to dealer (0)
    const nextSpeaker: 0 | 1 = currentSpeaker === 0 ? 1 : 0;
    setSpeaker(nextSpeaker);

    // 2. Check if Smart Buyer Bot triggered an automated honeypot or follow-up response
    const botText = result?.bot_response || result?.smart_bot?.dispatched_message;
    if (botText && currentSpeaker === 0) {
      setTimeout(() => {
        const botMessage: Message = {
          id: `bot-${Date.now()}`,
          sender: 1, // Undercover Buyer -> renders on the RIGHT!
          text: botText,
          time: Date.now(),
          origin: 'user',
        };
        setConversations((current) => appendMessagesToConversation(current, currentActiveId, [botMessage]));

        // When buyer bot sends its response, auto-shift composer back to dealer (0) for their turn
        setSpeaker(0);
        setNotice('Smart Buyer Bot responded with payment tracking link.');
      }, 700);
    }
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
    if (event.key === 'Escape') setEmojiPickerOpen(false);
  }

  async function handleAttachmentSelection(event: React.ChangeEvent<HTMLInputElement>, mode: 'images' | 'audio' | 'all') {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (!files.length) return;
    if (pendingAttachments.length + files.length > 4) { setNotice('Attach up to four files at a time.'); return; }
    const added: PendingAttachment[] = [];
    const documentMimeTypes = [
      'application/pdf', 'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/plain', 'text/rtf', 'application/rtf', 'text/csv', 'application/csv',
      'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ];
    for (const file of files) {
      const extension = file.name.toLowerCase().split('.').pop() ?? '';
      const audioExtensions = ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'oga', 'opus', 'webm', 'flac'];
      const documentExtensions = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'csv', 'xls', 'xlsx', 'ppt', 'pptx'];
      const kind: AttachmentKind | null = file.type.startsWith('image/') ? 'image'
        : file.type.startsWith('audio/') || audioExtensions.includes(extension) ? 'audio'
          : documentMimeTypes.includes(file.type) || documentExtensions.includes(extension) ? 'document'
            : null;
      if (!kind || (mode === 'images' && kind !== 'image') || (mode === 'audio' && kind !== 'audio')) {
        setNotice(mode === 'images' ? 'Choose image files only.' : mode === 'audio' ? 'Choose audio files only.' : `${file.name} is not a supported image, audio, or document file.`);
        continue;
      }
      if (file.size > 25 * 1024 * 1024) { setNotice(`${file.name} is larger than 25 MB.`); continue; }
      try {
        added.push(await prepareAttachment(file, kind));
      } catch { setNotice(`${file.name} could not be prepared as an attachment.`); }
    }
    if (added.length) {
      setPendingAttachments((current) => [...current, ...added].slice(0, 4));
      setNotice(`${added.length} attachment${added.length === 1 ? '' : 's'} ready to send.`);
    }
  }

  function removePendingAttachment(id: string) {
    setPendingAttachments((current) => {
      const removed = current.find((attachment) => attachment.id === id);
      if (removed) URL.revokeObjectURL(removed.previewUrl);
      return current.filter((attachment) => attachment.id !== id);
    });
  }

  function addEmoji(emoji: string) {
    setDraft((current) => `${current}${emoji}`);
    setEmojiPickerOpen(false);
    messageInput.current?.focus();
  }

  function selectConversation(id: string) {
    setActiveId(id);
    setSpeaker(0);
    setMobileShowChat(true);
    setOpenConversationMenu(null);
  }

  function deleteConversation() {
    if (!deleteCandidate) return;
    const removedConversation = deleteCandidate;
    const { remaining, removedAttachmentIds } = removeConversation(conversations, removedConversation.id);
    setConversations(remaining);
    if (activeId === removedConversation.id) {
      setActiveId(null);
      setMobileShowChat(false);
    }
    setOpenConversationMenu(null);
    setDeleteCandidate(null);
    setAttachmentSources((current) => {
      for (const id of removedAttachmentIds) if (current[id]) URL.revokeObjectURL(current[id]);
      return Object.fromEntries(Object.entries(current).filter(([id]) => !removedAttachmentIds.includes(id)));
    });
    void deleteStoredAttachments(removedAttachmentIds).catch(() => setNotice('The conversation was deleted, but a saved attachment could not be removed from browser storage.'));
    setNotice(`Conversation with ${removedConversation.people.join(' and ')} deleted.`);
  }

  const lastMessage = (conversation: Conversation) => conversation.messages[conversation.messages.length - 1];

  return (
    <main className="ig-app" data-theme={theme}>
      <aside className="icon-rail" aria-label="Main navigation">
        <a className="brand-mark" href="#messages" aria-label="Instagram messages home"><Icon name="instagram" size={30} /></a>
        <nav className="rail-nav" aria-label="Primary">
          {[['home', 'Home'], ['search', 'Search'], ['explore', 'Explore'], ['reels', 'Reels'], ['message', 'Messages'], ['heart', 'Notifications'], ['create', 'Create']].map(([icon, label]) => (
            <button className={`rail-button ${label === 'Messages' ? 'rail-button--active' : ''}`} key={label} aria-label={label} title={label} onClick={() => label === 'Messages' && setMobileShowChat(false)}>
              <Icon name={icon} /><span className="sr-only">{label}</span>{label === 'Messages' && conversations.length > 0 && <i className="rail-dot" />}
            </button>
          ))}
          <button className="rail-button theme-toggle" aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`} onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')}>
            <Icon name={theme === 'light' ? 'moon' : 'sun'} /><span className="sr-only">Switch to {theme === 'light' ? 'dark' : 'light'} mode</span>
          </button>
        </nav>
        <button className="rail-button rail-menu" aria-label="More options"><Icon name="menu" /></button>
      </aside>

      <section className={`inbox ${mobileShowChat ? 'inbox--hidden-mobile' : ''}`} aria-label="Messages inbox">
        <div className="inbox-top">
          <div className="instagram-wordmark" aria-label="Instagram"><Icon name="instagram" size={25} /><span>Instagram</span></div>
          <div className="stories-strip" role="group" aria-label="Fictional profile stories">{STORY_PROFILES.map((story) => <button className="story-tile" key={story.username} onClick={() => setActiveStory(story)} aria-label={`Open story for ${story.username}`}><span className={`story-ring story-ring--${story.art}`}><span className={`story-art story-art--${story.art}`} aria-hidden="true">{story.symbol}</span></span><span className="story-username">{story.username}</span></button>)}</div>
          <div className="account-row"><button className="account-name" aria-label="Current profile">your_messages <span aria-hidden="true">⌄</span></button><button className="new-message-button" onClick={() => setModalOpen(true)} aria-label="New message"><Icon name="create" /></button></div>
          <div className="inbox-heading"><h1>Messages</h1><button className="requests-button" onClick={() => setNotice('Message requests are not part of this local simulation.')}>Requests</button></div>
          <label className="search-box"><Icon name="search" size={18} /><span className="sr-only">Search conversations</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" /></label>
          <div className="inbox-tabs"><button className="tab tab--active" aria-current="page">Primary</button><button className="tab" onClick={() => setNotice('General inbox is not part of this simulation.')}>General</button><button className="tab" onClick={() => setNotice('Requests are not part of this simulation.')}>Requests</button></div>
        </div>
        <div className="conversation-list" role="list" aria-label="Conversations">
          {filteredConversations.length === 0 ? <div className="inbox-empty"><span className="empty-icon"><Icon name="message" size={30} /></span><strong>{conversations.length ? 'No matches' : 'Your messages'}</strong><p>{conversations.length ? 'Try another name.' : 'Start a conversation between two fictional participants.'}</p><button onClick={() => setModalOpen(true)}>New message</button></div> : filteredConversations.map((conversation) => {
            const latest = lastMessage(conversation);
            return <div role="listitem" className={`conversation-item ${activeId === conversation.id ? 'conversation-item--active' : ''}`} key={conversation.id}>
              <button className="conversation-open" onClick={() => selectConversation(conversation.id)} aria-current={activeId === conversation.id ? 'true' : undefined}>
                <span className="avatar-pair"><Avatar name={conversation.people[0]} size="large" /><Avatar name={conversation.people[1]} size="small" /></span>
                <span className="conversation-copy"><span className="conversation-names">{conversation.people.join(' · ')}</span><span className="conversation-preview">{latest ? `${conversation.people[latest.sender]}: ${latest.text || (getMessageAttachment(latest)?.kind === 'audio' ? 'Audio' : getMessageAttachment(latest)?.kind === 'document' ? 'Document' : getMessageAttachment(latest) ? 'Photo' : '')}` : 'Start a conversation'}</span></span>
                <span className="conversation-time">{latest ? formatTime(latest.time) : ''}</span>
              </button>
              <div className="conversation-actions">
                <button className="conversation-options" aria-label={`Options for conversation with ${conversation.people.join(' and ')}`} aria-haspopup="menu" aria-expanded={openConversationMenu === conversation.id} title="Conversation options" onClick={() => setOpenConversationMenu((current) => current === conversation.id ? null : conversation.id)}><Icon name="more" size={20} /></button>
                {openConversationMenu === conversation.id && <div className="conversation-menu" role="menu" aria-label={`Conversation options for ${conversation.people.join(' and ')}`}><button role="menuitem" onClick={() => { setDeleteCandidate(conversation); setOpenConversationMenu(null); }}>Delete conversation</button></div>}
              </div>
            </div>;
          })}
        </div>
        <button className="new-message-wide" onClick={() => setModalOpen(true)}><Icon name="create" size={18} /> New message</button>
        <div className="inbox-footer">Local simulation · Fictional participants</div>
      </section>

      <section className={`chat-pane ${mobileShowChat ? 'chat-pane--mobile-active' : ''}`} aria-label="Conversation">
        {!active ? <div className="welcome-state"><div className="welcome-message-icon"><Icon name="send" size={36} /></div><h2>Your messages</h2><p>Select a conversation or start a new one.</p><button className="primary-button" onClick={() => setModalOpen(true)}>Send message</button></div> : <>
          <header className="chat-header">
            <button className="mobile-back" onClick={() => setMobileShowChat(false)} aria-label="Back to inbox">‹</button>
            <span className="avatar-pair header-avatars"><Avatar name={active.people[0]} /><Avatar name={active.people[1]} size="small" /></span>
            <div className="header-names"><strong>{active.people.join(' · ')}</strong><span>Active now</span></div>
            <div className="header-actions"><button aria-label="Audio call" title="Audio call" onClick={() => setNotice('Calling is not part of this local simulation.')}><Icon name="phone" /></button><button aria-label="Video call" title="Video call" onClick={() => setNotice('Video calling is not part of this local simulation.')}><Icon name="video" /></button><button aria-label="Conversation information" title="Conversation information" onClick={() => setNotice(`A private local conversation between ${active.people.join(' and ')}.`)}><Icon name="info" /></button></div>
          </header>
          <div className="chat-body" aria-label="Message history" aria-live="polite">
            <div className="conversation-intro"><span className="avatar-pair intro-avatars"><Avatar name={active.people[0]} size="large" /><Avatar name={active.people[1]} size="large" /></span><h2>{active.people.join(' · ')}</h2><p>Instagram · Local conversation</p><span>Only you can see these messages in this browser.</span></div>
            {active.messages.length > 0 && <div className="message-divider">TODAY</div>}
            {active.messages.map((message, index) => {
              const previous = active.messages[index - 1];
              const grouped = previous?.sender === message.sender;
              const attachment = getMessageAttachment(message);
              const attachmentUrl = attachment ? attachmentSources[attachment.id] : undefined;
              return <div className={`message-row ${message.sender === 1 ? 'message-row--right' : ''} ${grouped ? 'message-row--grouped' : ''}`} key={message.id}>
                {message.sender === 0 && (grouped ? <span className="message-spacer" aria-hidden="true" /> : <Avatar name={active.people[0]} size="small" />)}
                {attachment?.kind === 'image' ? attachmentUrl
                  ? <img className="message-image" src={attachmentUrl} alt={`Image shared by ${active.people[message.sender]}: ${attachment.name}`} loading="lazy" />
                  : <div className="image-loading" role="status">Loading {attachment.name}…</div>
                  : attachment?.kind === 'audio' ? attachmentUrl
                    ? <div className={`message-bubble message-bubble--attachment ${message.sender === 1 ? 'message-bubble--sent' : ''}`} title={`${active.people[message.sender]} · ${formatTime(message.time)}`}><div className="attachment-message-title"><Icon name="mic" size={18} /><span>{attachment.name}</span></div><audio className="message-audio" controls preload="metadata" src={attachmentUrl}>Your browser cannot play this audio file.</audio><span className="attachment-message-size">{formatFileSize(attachment.sizeBytes)}</span></div>
                    : <div className="image-loading" role="status">Loading {attachment.name}…</div>
                    : attachment?.kind === 'document' ? attachmentUrl
                      ? <div className={`message-bubble message-bubble--attachment ${message.sender === 1 ? 'message-bubble--sent' : ''}`} title={`${active.people[message.sender]} · ${formatTime(message.time)}`}><a className="message-document" href={attachmentUrl} download={attachment.name}><span className="document-icon"><Icon name="attachment" size={20} /></span><span className="document-copy"><strong>{attachment.name}</strong><small>{formatFileSize(attachment.sizeBytes)} · {attachment.mimeType}</small></span></a></div>
                      : <div className="image-loading" role="status">Loading {attachment.name}…</div>
                      : <div className={`message-bubble ${message.sender === 1 ? 'message-bubble--sent' : ''}`} title={`${active.people[message.sender]} · ${formatTime(message.time)}`}>{renderMessageText(message.text)}</div>}
                {message.sender === 1 && (grouped ? <span className="message-spacer" aria-hidden="true" /> : <Avatar name={active.people[1]} size="small" />)}
              </div>;
            })}
            <div ref={messageEnd} />
          </div>
          <div className="composer-wrap">
            <div className="speaker-row"><label htmlFor="speaker-select">Sending as</label><select id="speaker-select" value={speaker} onChange={(event) => setSpeaker(Number(event.target.value) as 0 | 1)}><option value={0}>{active.people[0]} (Target/Dealer)</option><option value={1}>{active.people[1] === 'You' ? 'Undercover Buyer (You)' : `${active.people[1]} (Undercover Buyer)`}</option></select><span>· Auto-shifts turn after each message</span></div>
            {emojiPickerOpen && <div className="emoji-picker-popover"><EmojiPicker className="emoji-picker-widget" width="100%" height={390} colorScheme={theme} previewConfig={{ showPreview: false }} onEmojiClick={({ emoji }) => addEmoji(emoji)} /></div>}
            {pendingAttachments.length > 0 && <div className="attachment-previews" aria-label="Attachments ready to send">{pendingAttachments.map((attachment) => <div className={`attachment-preview attachment-preview--${attachment.kind}`} key={attachment.id}><div className="attachment-preview-media">{attachment.kind === 'image' ? <img src={attachment.previewUrl} alt={`Preview of ${attachment.name}`} /> : <><Icon name={attachment.kind === 'audio' ? 'mic' : 'attachment'} size={22} /><small>{attachment.kind === 'audio' ? 'Audio' : 'Document'}</small></>}</div><span title={attachment.name}>{attachment.name}</span><button type="button" aria-label={`Remove ${attachment.name}`} onClick={() => removePendingAttachment(attachment.id)}><Icon name="close" size={15} /></button></div>)}</div>}
            <input ref={imageInput} className="sr-only" type="file" accept="image/*" multiple aria-label="Choose images from your device" onChange={(event) => handleAttachmentSelection(event, 'images')} />
            <input ref={attachmentInput} className="sr-only" type="file" accept="image/*,audio/*,.pdf,.doc,.docx,.txt,.rtf,.csv,.xls,.xlsx,.ppt,.pptx" multiple aria-label="Choose image, audio, or document attachments" onChange={(event) => handleAttachmentSelection(event, 'all')} />
            <input ref={audioInput} className="sr-only" type="file" accept="audio/*" multiple aria-label="Choose audio files from your device" onChange={(event) => handleAttachmentSelection(event, 'audio')} />
            <form className="composer" onSubmit={sendMessage}>
              <button type="button" className="composer-icon" aria-label="Emoji" aria-haspopup="dialog" aria-expanded={emojiPickerOpen} onClick={() => setEmojiPickerOpen((open) => !open)}><Icon name="smile" /></button>
              <label className="sr-only" htmlFor="message-draft">Write a message</label>
              <textarea ref={messageInput} id="message-draft" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKey} placeholder="Message..." rows={1} maxLength={2000} />
              {draft.trim() ? <button type="submit" className="send-button">Send</button> : <div className="composer-tools"><button type="button" aria-label="Choose images from gallery" title="Choose images from gallery" onClick={() => imageInput.current?.click()}><Icon name="image" /></button><button type="button" aria-label="Attach a file" title="Attach image, audio, or document files" onClick={() => attachmentInput.current?.click()}><Icon name="attachment" /></button><button type="button" aria-label="Attach audio files" title="Attach audio files" onClick={() => audioInput.current?.click()}><Icon name="mic" /></button>{pendingAttachments.length > 0 && <button type="submit" className="send-button">Send</button>}</div>}
            </form>
            <p className="keyboard-hint">Press Enter to send · Shift + Enter for a new line</p>
          </div>
        </>}
      </section>

      {activeStory && <div className="modal-backdrop story-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setActiveStory(null)}>
        <section className="story-preview-modal" role="dialog" aria-modal="true" aria-labelledby="story-preview-title"><header><span className={`story-ring story-ring--${activeStory.art}`}><span className={`story-art story-art--${activeStory.art}`} aria-hidden="true">{activeStory.symbol}</span></span><div><h2 id="story-preview-title">{activeStory.username}</h2><p>Fictional story · Local simulation</p></div><button aria-label="Close story" onClick={() => setActiveStory(null)}><Icon name="close" /></button></header><div className={`story-preview-art story-art--${activeStory.art}`} aria-label={activeStory.caption}>{activeStory.symbol}<span>{activeStory.caption}</span></div></section>
      </div>}

      {modalOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setModalOpen(false)}>
        <section className="new-message-modal" role="dialog" aria-modal="true" aria-labelledby="new-message-title">
          <header><span /><h2 id="new-message-title">New message</h2><button aria-label="Close" onClick={() => setModalOpen(false)}><Icon name="close" /></button></header>
          <form onSubmit={createConversation}>
            <p>Create a local conversation with two fictional participants.</p>
            <label htmlFor="participant-one">First participant</label><input id="participant-one" autoFocus autoComplete="off" maxLength={32} value={firstName} onChange={(event) => setFirstName(event.target.value)} placeholder="e.g. Alex Rivera" required />
            <label htmlFor="participant-two">Second participant</label><input id="participant-two" autoComplete="off" maxLength={32} value={secondName} onChange={(event) => setSecondName(event.target.value)} placeholder="e.g. Jordan Lee" required />
            <button className="primary-button modal-submit" type="submit">Create conversation</button>
          </form>
        </section>
      </div>}
      {deleteCandidate && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setDeleteCandidate(null)}>
        <section className="delete-confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-conversation-title" aria-describedby="delete-conversation-description">
          <h2 id="delete-conversation-title">Delete conversation?</h2>
          <p id="delete-conversation-description">This will remove the conversation between {deleteCandidate.people[0]} and {deleteCandidate.people[1]}, including its messages, from this browser.</p>
          <div className="delete-confirm-actions"><button className="cancel-delete" onClick={() => setDeleteCandidate(null)}>Cancel</button><button className="confirm-delete" onClick={deleteConversation}>Delete</button></div>
        </section>
      </div>}
      <div className="sr-only" role="status" aria-live="polite">{notice}</div>
      {notice && <button className="toast" onClick={() => setNotice('')} aria-label={`Dismiss message: ${notice}`}><span>{notice}</span><Icon name="close" size={16} /></button>}
    </main>
  );
}
