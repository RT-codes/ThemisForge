// The parts of the agent editor. The page shows the tabs above the panel, the form shows the part that is chosen.

export type AgentTab = 'general' | 'skills' | 'tools'

/** what the tabs say about the agent being edited, and which of them its harness has at all */
export type AgentCounts = { skills: number; tools: number; hasSkills: boolean; hasTools: boolean }
