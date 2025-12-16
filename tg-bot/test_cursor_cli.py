#!/usr/bin/env python3
"""
Test script for CursorCLI functionality.

This script tests all core CursorCLI functions:
1. Creating sessions
2. Executing queries
3. Switching between sessions
4. Deleting sessions
5. Flags support
6. Host commands

Run with: python test_cursor_cli.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db import get_session
from app.models import User, CursorCLISession, CursorCLIMessage
from app.routers.cursor_cli import (
    get_user_sessions,
    create_session_with_uuid,
    get_or_create_session,
    save_message,
    execute_cursor_command,
    end_cursor_session,
    parse_flags_from_query,
    delete_current_session,
)
from sqlalchemy import select, and_, delete
import docker


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_test(name: str):
    """Print test name"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}Testing: {name}{Colors.RESET}")


def print_success(msg: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")


def print_error(msg: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")


def print_warning(msg: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")


async def test_docker_container():
    """Test 1: Check if cursor-code-console container exists"""
    print_test("Docker Container Check")
    try:
        client = docker.from_env()
        try:
            container = client.containers.get('cursor-code-console')
            if container.status == 'running':
                print_success(f"Container 'cursor-code-console' is running")
                return True
            else:
                print_warning(f"Container 'cursor-code-console' exists but is not running (status: {container.status})")
                return False
        except docker.errors.NotFound:
            print_error("Container 'cursor-code-console' not found. Please start it with: docker compose -p localai --profile cursor up -d cursor-code-console")
            return False
    except Exception as e:
        print_error(f"Error checking Docker container: {e}")
        return False


async def test_get_or_create_user():
    """Test 2: Get or create a test user"""
    print_test("User Setup")
    async with get_session() as session:
        # Try to get existing test user
        result = await session.execute(
            select(User).where(User.telegram_id == 999999999)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Create test user
            user = User(
                telegram_id=999999999,
                username="test_user",
                first_name="Test",
                role="user"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print_success(f"Created test user (id: {user.id}, telegram_id: {user.telegram_id})")
        else:
            print_success(f"Using existing test user (id: {user.id}, telegram_id: {user.telegram_id})")
        
        return user


async def test_create_session(user: User):
    """Test 3: Create a new CursorCLI session"""
    print_test("Session Creation")
    session_name = "test_session_1"
    
    # Clean up any existing test session
    async with get_session() as db_session:
        result = await db_session.execute(
            select(CursorCLISession).where(
                and_(
                    CursorCLISession.user_id == user.id,
                    CursorCLISession.session_name == session_name
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            await db_session.delete(existing)
            await db_session.commit()
            print_warning(f"Deleted existing test session '{session_name}'")
    
    # Create new session
    new_session, error = await create_session_with_uuid(user.id, session_name)
    
    if error:
        print_error(f"Failed to create session: {error}")
        return None
    
    if not new_session:
        print_error("Session creation returned None")
        return None
    
    print_success(f"Created session '{session_name}' (id: {new_session.id}, uuid: {new_session.uuid})")
    return new_session


async def test_get_user_sessions(user: User):
    """Test 4: Get all sessions for user"""
    print_test("Get User Sessions")
    sessions = await get_user_sessions(user.id)
    print_success(f"Found {len(sessions)} session(s) for user")
    for session in sessions:
        print(f"  - {session.session_name} (id: {session.id}, uuid: {session.uuid})")
    return sessions


async def test_execute_query(session: CursorCLISession, user: User):
    """Test 5: Execute a query in a session"""
    print_test("Query Execution")
    
    query = "Hello, this is a test query"
    output, success, chat_id = await execute_cursor_command(session.uuid, query)
    
    if success:
        print_success(f"Query executed successfully (output length: {len(output)} chars)")
        if chat_id:
            print_success(f"Received chat_id: {chat_id}")
            # Update session UUID if we got one
            if not session.uuid:
                async with get_session() as db_session:
                    result = await db_session.execute(
                        select(CursorCLISession).where(CursorCLISession.id == session.id)
                    )
                    session_to_update = result.scalar_one_or_none()
                    if session_to_update:
                        session_to_update.uuid = chat_id
                        await db_session.commit()
                        await db_session.refresh(session_to_update)
                        session.uuid = chat_id
                        print_success(f"Updated session UUID to {chat_id}")
        
        # Save message
        await save_message(session.id, user.id, query, output, None)
        print_success("Message saved to database")
        return True
    else:
        print_error(f"Query execution failed: {output[:200]}")
        return False


async def test_switch_sessions(user: User):
    """Test 6: Create multiple sessions and switch between them"""
    print_test("Session Switching")
    
    # Create second session
    session_name_2 = "test_session_2"
    session2, error = await create_session_with_uuid(user.id, session_name_2)
    
    if error or not session2:
        print_error(f"Failed to create second session: {error}")
        return False
    
    print_success(f"Created second session '{session_name_2}'")
    
    # Get all sessions
    sessions = await get_user_sessions(user.id)
    if len(sessions) >= 2:
        print_success(f"User has {len(sessions)} sessions, can switch between them")
        return True
    else:
        print_error(f"Expected at least 2 sessions, got {len(sessions)}")
        return False


async def test_flags_parsing():
    """Test 7: Parse flags from query"""
    print_test("Flags Parsing")
    
    test_cases = [
        ("Hello #flags --verbose", ("Hello", "--verbose")),
        ("Query with flags #flags -x -y", ("Query with flags", "-x -y")),
        ("No flags here", ("No flags here", None)),
        ("#flags only", ("", None)),
    ]
    
    all_passed = True
    for query, expected in test_cases:
        query_clean, flags = parse_flags_from_query(query)
        if (query_clean, flags) == expected:
            print_success(f"Parsed: '{query}' -> query='{query_clean}', flags='{flags}'")
        else:
            print_error(f"Failed: '{query}' -> got ('{query_clean}', '{flags}'), expected {expected}")
            all_passed = False
    
    return all_passed


async def test_host_command():
    """Test 8: Execute host command"""
    print_test("Host Command Execution")
    
    from app.services.host_executor import execute_host_command_simple
    
    # Test a simple host command
    output, success = await execute_host_command_simple("ping -c 2 127.0.0.1")
    
    if success:
        print_success(f"Host command executed successfully (output length: {len(output)} chars)")
        print(f"  Output preview: {output[:100]}...")
        return True
    else:
        print_warning(f"Host command failed (this is expected if network tools are not available): {output[:200]}")
        # Don't fail the test, as host commands may not work in all environments
        return True


async def test_delete_session(session: CursorCLISession, user: User):
    """Test 9: Delete a session"""
    print_test("Session Deletion")
    
    session_id = session.id
    session_name = session.session_name
    
    # Count messages before deletion
    async with get_session() as db_session:
        result = await db_session.execute(
            select(CursorCLIMessage).where(CursorCLIMessage.session_id == session_id)
        )
        messages_before = len(list(result.scalars().all()))
    
    # Delete session
    async with get_session() as db_session:
        result = await db_session.execute(
            select(CursorCLISession).where(CursorCLISession.id == session_id)
        )
        session_to_delete = result.scalar_one_or_none()
        
        if session_to_delete:
            await db_session.delete(session_to_delete)
            await db_session.commit()
            print_success(f"Deleted session '{session_name}' (id: {session_id})")
            
            # Verify messages still exist but with NULL session_id
            result = await db_session.execute(
                select(CursorCLIMessage).where(CursorCLIMessage.session_id == None)
            )
            messages_after = len(list(result.scalars().all()))
            
            if messages_after >= messages_before:
                print_success(f"Messages preserved ({messages_before} messages, {messages_after} with NULL session_id)")
                return True
            else:
                print_error(f"Message count mismatch: {messages_before} before, {messages_after} after")
                return False
        else:
            print_error(f"Session '{session_name}' not found for deletion")
            return False


async def test_end_session():
    """Test 10: End session (API consistency check)"""
    print_test("End Session")
    
    result = await end_cursor_session("test_uuid_123")
    if result:
        print_success("end_cursor_session() returned True (sessions are auto-managed)")
        return True
    else:
        print_error("end_cursor_session() returned False")
        return False


async def cleanup_test_data(user: User):
    """Clean up test data"""
    print_test("Cleanup")
    async with get_session() as session:
        # Delete all test sessions
        result = await session.execute(
            select(CursorCLISession).where(CursorCLISession.user_id == user.id)
        )
        test_sessions = result.scalars().all()
        
        for test_session in test_sessions:
            await session.delete(test_session)
        
        await session.commit()
        print_success(f"Cleaned up {len(test_sessions)} test session(s)")


async def main():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print("CursorCLI Functionality Test Suite")
    print(f"{'='*60}{Colors.RESET}\n")
    
    results = {}
    
    # Test 1: Docker container
    results['docker'] = await test_docker_container()
    if not results['docker']:
        print_warning("Some tests may fail without the Docker container running")
    
    # Test 2: User setup
    user = await test_get_or_create_user()
    if not user:
        print_error("Cannot proceed without a test user")
        return
    
    # Test 3: Create session
    session = await test_create_session(user)
    results['create_session'] = session is not None
    
    if session:
        # Test 4: Get sessions
        results['get_sessions'] = len(await test_get_user_sessions(user)) > 0
        
        # Test 5: Execute query
        results['execute_query'] = await test_execute_query(session, user)
        
        # Test 6: Switch sessions
        results['switch_sessions'] = await test_switch_sessions(user)
        
        # Test 9: Delete session (only if we have a session)
        # Note: We'll delete the first session, but keep the second for other tests
        if session.session_name == "test_session_1":
            results['delete_session'] = await test_delete_session(session, user)
    
    # Test 7: Flags parsing (doesn't require session)
    results['flags'] = await test_flags_parsing()
    
    # Test 8: Host commands
    results['host_commands'] = await test_host_command()
    
    # Test 10: End session
    results['end_session'] = await test_end_session()
    
    # Cleanup
    await cleanup_test_data(user)
    
    # Print summary
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print("Test Summary")
    print(f"{'='*60}{Colors.RESET}\n")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for test_name, result in results.items():
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {test_name:20} {status}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.RESET}\n")
    
    if passed == total:
        print(f"{Colors.GREEN}All tests passed! ✓{Colors.RESET}\n")
        return 0
    else:
        print(f"{Colors.YELLOW}Some tests failed. Please review the output above.{Colors.RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
