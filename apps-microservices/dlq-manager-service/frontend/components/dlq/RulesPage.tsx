"use client"

import * as React from "react";
import { useState, useEffect } from "react"
import { apiGetRules, apiToggleRule, apiDeleteRule, AutoArchiveRule } from "@/lib/api"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { Trash2, AlertCircle, Eye } from "lucide-react"

interface RulesPageProps {
  onViewRuleMatches?: (rule: AutoArchiveRule) => void;
}

export default function RulesPage({ onViewRuleMatches }: RulesPageProps) {
    const formatRelativeTime = (isoString?: string | null): string => {
        if (!isoString) return "Never";
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffSec = Math.floor(diffMs / 1000);

        if (diffSec < 60) return `${diffSec}s ago`;
        const diffMin = Math.floor(diffSec / 60);
        if (diffMin < 60) return `${diffMin}m ago`;
        const diffHr = Math.floor(diffMin / 60);
        if (diffHr < 24) return `${diffHr}h ago`;

        return date.toLocaleString();
    };

    const [rules, setRules] = useState<AutoArchiveRule[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchRules = async () => {
        try {
            setLoading(true);
            const res = await apiGetRules();
            setRules(res.data);
        } catch (error) {
            console.error("Failed to load rules", error);
            alert("Failed to load rules.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRules();
    }, []);

    const handleToggle = async (ruleId: string, currentStatus: boolean) => {
        try {
            // Optimistic update using functional updater to avoid stale closure
            setRules(prev => prev.map(r => r._id === ruleId ? { ...r, is_active: !currentStatus } : r));
            await apiToggleRule(ruleId, !currentStatus);
        } catch (error) {
            alert("Failed to update rule status.");
            fetchRules(); // Revert on failure
        }
    };

    const handleDelete = async (ruleId: string) => {
        if (!window.confirm("Are you sure you want to permanently delete this rule?")) return;
        try {
            await apiDeleteRule(ruleId);
            setRules(prev => prev.filter(r => r._id !== ruleId));
        } catch (error) {
            alert("Failed to delete rule.");
        }
    };

    if (loading) return <div className="p-8 text-center text-gris-primary">Loading rules...</div>;

    return (
        <div className="p-4 md:p-8 space-y-6">
            <div className="bg-bleu-light border border-bleu-primary/20 p-4 rounded-lg flex gap-3 text-sm text-noir-primary">
                <AlertCircle className="w-5 h-5 text-bleu-primary shrink-0" />
                <p>
                    Auto-Archive Rules automatically move <strong>"New"</strong> messages matching specific queries to the 
                    <span className="font-semibold text-gris-primary bg-clair-4 px-2 py-0.5 rounded mx-1">Auto-Archived</span> 
                    status. The background engine checks for new matches every minute.
                </p>
            </div>

            {rules.length === 0 ? (
                <div className="text-center p-8 border border-dashed border-gris-blanc rounded-lg bg-white-primary">
                    <p className="text-gris-primary">No rules configured yet.</p>
                    <p className="text-sm mt-2 text-noir-primary">You can create a rule directly from the "Search & Re-queue" page.</p>
                </div>
            ) : (
                <div className="bg-white-primary rounded-lg border border-gris-blanc overflow-x-auto w-full">
                    <table className="w-full min-w-[1100px]">
                        <thead>
                            <tr className="border-b border-gris-blanc bg-clair-4">
                                <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Rule Name & Description</th>
                                <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Target Conditions</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Executions</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Last Checked</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Last Archived</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Active</th>
                                <th className="px-6 py-4 text-center text-sm font-semibold text-noir-primary">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rules.map((rule) => (
                                <tr key={rule._id} className="border-b border-gris-blanc hover:bg-clair-4 transition-colors">
                                    <td className="px-6 py-4">
                                        <p className="font-semibold text-noir-primary text-sm">{rule.name}</p>
                                        {rule.description && (
                                            <p className="text-xs text-gris-primary mt-1 line-clamp-2" title={rule.description}>{rule.description}</p>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-xs font-mono text-gris-primary break-all">
                                        {rule.search_term && <div><span className="font-semibold text-noir-primary">Query:</span> {rule.search_term}</div>}
                                        {rule.filters && Object.keys(rule.filters).length > 0 && (
                                            <div className="mt-1"><span className="font-semibold text-noir-primary">Filters:</span> {JSON.stringify(rule.filters)}</div>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-center text-sm font-medium text-bleu-primary">
                                        {rule.execution_count?.toLocaleString() || 0}
                                    </td>
                                    <td className="px-6 py-4 text-center text-xs text-gris-primary whitespace-nowrap" title={rule.last_evaluated_at || "Never"}>
                                        {formatRelativeTime(rule.last_evaluated_at)}
                                    </td>
                                    <td className="px-6 py-4 text-center text-xs text-gris-primary whitespace-nowrap" title={rule.last_archived_at || "Never"}>
                                        {formatRelativeTime(rule.last_archived_at)}
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <Switch
                                            checked={rule.is_active}
                                            onCheckedChange={() => rule._id && handleToggle(rule._id, rule.is_active)}
                                        />
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <div className="flex items-center justify-center gap-1">
                                            {onViewRuleMatches && (
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => onViewRuleMatches(rule)}
                                                    className="text-bleu-primary hover:bg-bleu-light hover:text-bleu-primary"
                                                    aria-label={`View messages matched by rule ${rule.name}`}
                                                    title="View matched messages"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </Button>
                                            )}
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => rule._id && handleDelete(rule._id)}
                                                className="text-rouge-primary hover:bg-rouge-light hover:text-rouge-primary"
                                                aria-label={`Delete rule ${rule.name}`}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}