//! Pure graph helpers for `blocks` links.

use std::collections::{HashMap, HashSet};

use crate::model::Id;

/// Would adding the edge `from -> to` (from blocks to) create a cycle in `edges`?
/// A self-loop is a cycle.
pub fn would_create_cycle(edges: &[(Id, Id)], from: Id, to: Id) -> bool {
    if from == to {
        return true;
    }
    let mut adj: HashMap<Id, Vec<Id>> = HashMap::new();
    for &(a, b) in edges {
        adj.entry(a).or_default().push(b);
    }
    // A cycle appears iff `from` is already reachable from `to`.
    let mut seen: HashSet<Id> = HashSet::new();
    let mut stack = vec![to];
    while let Some(node) = stack.pop() {
        if node == from {
            return true;
        }
        if !seen.insert(node) {
            continue;
        }
        if let Some(next) = adj.get(&node) {
            stack.extend(next.iter().copied());
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn detects_transitive_cycle_and_allows_dag() {
        let (a, b, c, d) = (
            Uuid::now_v7(),
            Uuid::now_v7(),
            Uuid::now_v7(),
            Uuid::now_v7(),
        );
        let edges = vec![(a, b), (b, c)];
        assert!(would_create_cycle(&edges, c, a));
        assert!(would_create_cycle(&edges, a, a));
        assert!(!would_create_cycle(&edges, a, c));
        assert!(!would_create_cycle(&edges, d, a));
    }
}
