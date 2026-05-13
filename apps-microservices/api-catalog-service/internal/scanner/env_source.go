package scanner

type Target struct {
	Name    string
	BaseURL string
	Source  string
}

type DBRow struct {
	Name    string
	BaseURL string
	Source  string
}

func MergeTargets(envSeeds map[string]string, dbRows []DBRow) []Target {
	seen := map[string]Target{}
	for name, url := range envSeeds {
		seen[name] = Target{Name: name, BaseURL: url, Source: "env"}
	}
	for _, r := range dbRows {
		if r.Source == "manual" {
			if _, exists := seen[r.Name]; !exists {
				seen[r.Name] = Target{Name: r.Name, BaseURL: r.BaseURL, Source: "manual"}
			}
		}
	}
	out := make([]Target, 0, len(seen))
	for _, t := range seen {
		out = append(out, t)
	}
	return out
}
