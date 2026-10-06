import BotIcon from '@lucide/svelte/icons/bot'
import FlagIcon from '@lucide/svelte/icons/flag'
import GitBranchIcon from '@lucide/svelte/icons/git-branch'
import ListChecksIcon from '@lucide/svelte/icons/list-checks'
import RocketIcon from '@lucide/svelte/icons/rocket'
import ZapIcon from '@lucide/svelte/icons/zap'
import type { NodeKind } from './workflow'

export const nodeIcons = { start: RocketIcon, trigger: ZapIcon, task: ListChecksIcon, agent: BotIcon, condition: GitBranchIcon, end: FlagIcon } satisfies Record<NodeKind, typeof ZapIcon>
