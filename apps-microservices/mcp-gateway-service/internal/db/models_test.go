package db

import "testing"

func TestServerToolTableName(t *testing.T) {
	st := ServerTool{}
	if st.TableName() != "server_tools" {
		t.Errorf("expected table name 'server_tools', got '%s'", st.TableName())
	}
}

func TestServerToolIsActiveDefault(t *testing.T) {
	st := ServerTool{}
	// Zero value for bool is false, but GORM default is true.
	// This test documents the expected GORM tag behavior.
	if st.IsActive {
		t.Error("zero-value ServerTool should have IsActive=false (GORM applies default at DB level)")
	}
}
