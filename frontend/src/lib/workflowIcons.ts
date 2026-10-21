import BotIcon from '@lucide/svelte/icons/bot'
import BrainIcon from '@lucide/svelte/icons/brain'
import CircleDotIcon from '@lucide/svelte/icons/circle-dot'
import ClipboardListIcon from '@lucide/svelte/icons/clipboard-list'
import ClockIcon from '@lucide/svelte/icons/clock'
import ContainerIcon from '@lucide/svelte/icons/container'
import CpuIcon from '@lucide/svelte/icons/cpu'
import FlagIcon from '@lucide/svelte/icons/flag'
import FolderIcon from '@lucide/svelte/icons/folder'
import FolderInputIcon from '@lucide/svelte/icons/folder-input'
import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
import FoldersIcon from '@lucide/svelte/icons/folders'
import GitBranchIcon from '@lucide/svelte/icons/git-branch'
import HeadingIcon from '@lucide/svelte/icons/heading'
import LayoutDashboardIcon from '@lucide/svelte/icons/layout-dashboard'
import LinkIcon from '@lucide/svelte/icons/link'
import ListChecksIcon from '@lucide/svelte/icons/list-checks'
import MergeIcon from '@lucide/svelte/icons/merge'
import ShieldCheckIcon from '@lucide/svelte/icons/shield-check'
import LockIcon from '@lucide/svelte/icons/lock'
import MapPinIcon from '@lucide/svelte/icons/map-pin'
import NotepadTextIcon from '@lucide/svelte/icons/notepad-text'
import RepeatIcon from '@lucide/svelte/icons/repeat'
import RocketIcon from '@lucide/svelte/icons/rocket'
import ScaleIcon from '@lucide/svelte/icons/scale'
import SearchIcon from '@lucide/svelte/icons/search'
import SplitIcon from '@lucide/svelte/icons/split'
import StickyNoteIcon from '@lucide/svelte/icons/sticky-note'
import TagIcon from '@lucide/svelte/icons/tag'
import TerminalIcon from '@lucide/svelte/icons/terminal'
import TextAlignStartIcon from '@lucide/svelte/icons/text-align-start'
import TextCursorInputIcon from '@lucide/svelte/icons/text-cursor-input'
import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
import ZapIcon from '@lucide/svelte/icons/zap'
import type { NodeKind } from './workflow'

export const nodeIcons = { start: RocketIcon, trigger: ZapIcon, task: ListChecksIcon, agent: BotIcon, condition: GitBranchIcon, approval: ShieldCheckIcon, end: FlagIcon, volume: FolderIcon, split: SplitIcon, merge: MergeIcon } satisfies Record<NodeKind, typeof ZapIcon>

/**
 * The icon in front of each setting in a node's window, by the setting's key (see NODE_FIELDS in workflow.ts). A key
 * means the same thing on every kind that has it, so one icon serves them all. `name` and `cell` are the two labels the
 * window draws itself, and `handedOver` the folders joined on the canvas. A setting without an entry just shows no icon.
 */
export const fieldIcons: Record<string, typeof ZapIcon> = {
  name: TagIcon,
  // Trigger
  type: ZapIcon,
  repeat: RepeatIcon,
  time: ClockIcon,
  status: CircleDotIcon,
  where: MapPinIcon,
  // Task
  action: ListChecksIcon,
  title: HeadingIcon,
  description: TextAlignStartIcon,
  boardId: LayoutDashboardIcon,
  link: LinkIcon,
  workdir: FolderOpenIcon,
  // Agent
  agentId: BotIcon,
  harness: TerminalIcon,
  instructions: NotepadTextIcon,
  brief: ClipboardListIcon,
  onFailure: TriangleAlertIcon,
  model: CpuIcon,
  reasoningEffort: BrainIcon,
  mounts: FoldersIcon,
  cell: ContainerIcon,
  handedOver: FolderInputIcon,
  // Condition
  source: SearchIcon,
  operator: ScaleIcon,
  value: TextCursorInputIcon,
  // Folder
  volumeId: FolderIcon,
  mode: LockIcon,
  // Splitter and Merger (their per-branch settings are name1, contains1... and use the icon of the key without the number)
  branches: SplitIcon,
  contains: SearchIcon,
  files: FolderOpenIcon,
  // End
  outcome: FlagIcon,
  note: StickyNoteIcon,
}
