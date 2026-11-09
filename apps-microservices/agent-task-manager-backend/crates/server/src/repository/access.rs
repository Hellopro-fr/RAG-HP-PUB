//! Access settings (`access_rules`) and the human accounts they apply to.

use sqlx::PgConnection;
use uuid::Uuid;

use crate::actor::Actor;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuleRow {
    pub subject_kind: String,
    pub subject_id: String,
    pub permission: String,
    pub effect: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HumanRow {
    pub id: Uuid,
    pub name: String,
    pub login: Option<String>,
    pub roles: Vec<String>,
}

/// Settings of the given subjects (one kind).
pub async fn rules_for(
    conn: &mut PgConnection,
    kind: &str,
    ids: &[String],
) -> Result<Vec<RuleRow>, sqlx::Error> {
    sqlx::query_as!(
        RuleRow,
        r#"SELECT subject_kind, subject_id, permission, effect FROM access_rules
           WHERE subject_kind = $1 AND subject_id = ANY($2)
           ORDER BY subject_id, permission"#,
        kind,
        ids
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn all_rules(conn: &mut PgConnection) -> Result<Vec<RuleRow>, sqlx::Error> {
    sqlx::query_as!(
        RuleRow,
        r#"SELECT subject_kind, subject_id, permission, effect FROM access_rules
           ORDER BY subject_kind, subject_id, permission"#
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn set_rule(
    conn: &mut PgConnection,
    kind: &str,
    id: &str,
    permission: &str,
    effect: &str,
    by: Uuid,
) -> Result<(), sqlx::Error> {
    sqlx::query!(
        r#"INSERT INTO access_rules (subject_kind, subject_id, permission, effect, updated_by)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (subject_kind, subject_id, permission)
           DO UPDATE SET effect = EXCLUDED.effect, updated_by = EXCLUDED.updated_by,
                         updated_at = now()"#,
        kind,
        id,
        permission,
        effect,
        by
    )
    .execute(&mut *conn)
    .await?;
    Ok(())
}

pub async fn delete_rule(
    conn: &mut PgConnection,
    kind: &str,
    id: &str,
    permission: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query!(
        "DELETE FROM access_rules WHERE subject_kind = $1 AND subject_id = $2 AND permission = $3",
        kind,
        id,
        permission
    )
    .execute(&mut *conn)
    .await?;
    Ok(())
}

/// Every human account, by name.
pub async fn humans(conn: &mut PgConnection) -> Result<Vec<HumanRow>, sqlx::Error> {
    sqlx::query_as!(
        HumanRow,
        "SELECT id, name, login, roles FROM actors WHERE kind = 'human' ORDER BY lower(name), id"
    )
    .fetch_all(&mut *conn)
    .await
}

pub async fn human(conn: &mut PgConnection, id: Uuid) -> Result<Option<HumanRow>, sqlx::Error> {
    sqlx::query_as!(
        HumanRow,
        "SELECT id, name, login, roles FROM actors WHERE kind = 'human' AND id = $1",
        id
    )
    .fetch_optional(&mut *conn)
    .await
}

/// The human whose login is this email (HelloPro sign-in), case-insensitive.
pub async fn human_by_login(
    conn: &mut PgConnection,
    login: &str,
) -> Result<Option<Actor>, sqlx::Error> {
    let r = sqlx::query!(
        r#"SELECT id, kind, name, roles, model FROM actors
           WHERE kind = 'human' AND lower(login) = lower($1)
           ORDER BY created_at LIMIT 1"#,
        login
    )
    .fetch_optional(&mut *conn)
    .await?;
    Ok(r.map(|r| Actor::from_row(r.id, &r.kind, r.name, &r.roles, r.model)))
}

pub async fn set_roles(
    conn: &mut PgConnection,
    id: Uuid,
    roles: &[String],
) -> Result<(), sqlx::Error> {
    sqlx::query!(
        "UPDATE actors SET roles = $2, updated_at = now() WHERE id = $1 AND kind = 'human'",
        id,
        roles
    )
    .execute(&mut *conn)
    .await?;
    Ok(())
}

/// Number of human admins, rows locked so two demotions cannot both pass the "last admin" check.
pub async fn lock_admin_humans(conn: &mut PgConnection) -> Result<i64, sqlx::Error> {
    let ids = sqlx::query_scalar!(
        "SELECT id FROM actors WHERE kind = 'human' AND 'admin' = ANY(roles) FOR UPDATE"
    )
    .fetch_all(&mut *conn)
    .await?;
    Ok(ids.len() as i64)
}
