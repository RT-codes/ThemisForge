import BotIcon from '@lucide/svelte/icons/bot'
import FlagIcon from '@lucide/svelte/icons/flag'
import GitBranchIcon from '@lucide/svelte/icons/git-branch'
import ListChecksIcon from '@lucide/svelte/icons/list-checks'
import PlayIcon from '@lucide/svelte/icons/play'
import ZapIcon from '@lucide/svelte/icons/zap'
import type { NodeKind } from './workflow'

export const nodeIcons = { start: PlayIcon, trigger: ZapIcon, task: ListChecksIcon, agent: BotIcon, condition: GitBranchIcon, end: FlagIcon } satisfies Record<NodeKind, typeof ZapIcon>
