//! §3: `events` is append-only for the application's database role (atb_app): INSERT and SELECT
//! work, UPDATE and DELETE are refused. Positive controls prove the statements themselves are valid.

use sqlx::{Connection, PgPool};
use uuid::Uuid;

#[sqlx::test(migrations = "../../migrations")]
async fn app_role_cannot_rewrite_history(pool: PgPool) {
    let project = Uuid::now_v7();
    sqlx::query("INSERT INTO projects (id, name, workflow) VALUES ($1, 'p', '{}')")
        .bind(project)
        .execute(&pool)
        .await
        .unwrap();
    let mut conn = pool.acquire().await.unwrap();
    let mut tx = conn.begin().await.unwrap();
    sqlx::query("SET LOCAL ROLE atb_app")
        .execute(&mut *tx)
        .await
        .unwrap();
    // Positive control: the app role can append and read.
    sqlx::query(
        "INSERT INTO events (project_id, seq, type, actor_id, payload, created_at)
         VALUES ($1, 1, 'task.created', '00000000-0000-7000-8000-000000000001', '{}', now())",
    )
    .bind(project)
    .execute(&mut *tx)
    .await
    .expect("atb_app can insert events");
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM events")
        .fetch_one(&mut *tx)
        .await
        .unwrap();
    assert_eq!(n, 1);
    // It cannot rewrite them.
    sqlx::query("SAVEPOINT s").execute(&mut *tx).await.unwrap();
    let err = sqlx::query("UPDATE events SET type = 'forged'")
        .execute(&mut *tx)
        .await
        .expect_err("UPDATE must be refused");
    assert!(err.to_string().contains("permission denied"), "{err}");
    sqlx::query("ROLLBACK TO SAVEPOINT s")
        .execute(&mut *tx)
        .await
        .unwrap();
    let err = sqlx::query("DELETE FROM events")
        .execute(&mut *tx)
        .await
        .expect_err("DELETE must be refused");
    assert!(err.to_string().contains("permission denied"), "{err}");
    tx.rollback().await.unwrap();

    // Positive control: the same UPDATE is valid SQL for the owner role.
    sqlx::query(
        "INSERT INTO events (project_id, seq, type, actor_id, payload, created_at)
         VALUES ($1, 1, 'task.created', '00000000-0000-7000-8000-000000000001', '{}', now())",
    )
    .bind(project)
    .execute(&pool)
    .await
    .unwrap();
    let updated = sqlx::query("UPDATE events SET type = 'forged'")
        .execute(&pool)
        .await
        .unwrap();
    assert_eq!(updated.rows_affected(), 1);
}
