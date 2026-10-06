import BotIcon from '@lucide/svelte/icons/bot'
import FlagIcon from '@lucide/svelte/icons/flag'
import FolderIcon from '@lucide/svelte/icons/folder'
import GitBranchIcon from '@lucide/svelte/icons/git-branch'
import ListChecksIcon from '@lucide/svelte/icons/list-checks'
import RocketIcon from '@lucide/svelte/icons/rocket'
import ZapIcon from '@lucide/svelte/icons/zap'
import type { NodeKind } from './workflow'

export const nodeIcons = { start: RocketIcon, trigger: ZapIcon, task: ListChecksIcon, agent: BotIcon, condition: GitBranchIcon, end: FlagIcon, volume: FolderIcon } satisfies Record<NodeKind, typeof ZapIcon>
