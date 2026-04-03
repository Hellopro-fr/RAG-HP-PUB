package mcp

// AggregateCapabilities merges server capabilities from multiple backends.
// A capability is present if at least one backend supports it.
func AggregateCapabilities(caps []ServerCapabilities) ServerCapabilities {
	var result ServerCapabilities

	for _, c := range caps {
		if c.Tools != nil {
			if result.Tools == nil {
				result.Tools = &ToolsCapability{}
			}
			if c.Tools.ListChanged {
				result.Tools.ListChanged = true
			}
		}
		if c.Resources != nil {
			if result.Resources == nil {
				result.Resources = &ResourcesCapability{}
			}
			if c.Resources.Subscribe {
				result.Resources.Subscribe = true
			}
			if c.Resources.ListChanged {
				result.Resources.ListChanged = true
			}
		}
		if c.Prompts != nil {
			if result.Prompts == nil {
				result.Prompts = &PromptsCapability{}
			}
			if c.Prompts.ListChanged {
				result.Prompts.ListChanged = true
			}
		}
	}

	return result
}
