"""
Tests for authentication module.
"""
import unittest
import tempfile
import os
import sys
import yaml
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.authentication import (
    AuthenticationManager, 
    load_config, 
    persist_access_token,
    _substitute_env
)


class TestAuthenticationManager(unittest.TestCase):
    """Test cases for AuthenticationManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'zerodha': {
                'api_key': 'test_api_key',
                'api_secret': 'test_api_secret',
                'access_token': ''
            }
        }
        self.auth_manager = AuthenticationManager(self.config)
    
    def test_initialization(self):
        """Test AuthenticationManager initialization."""
        self.assertIsNotNone(self.auth_manager.kite)
        self.assertEqual(self.auth_manager.config, self.config)
    
    @patch('core.authentication.KiteConnect')
    def test_adopt_access_token_success(self, mock_kite):
        """Test successful access token adoption."""
        mock_kite_instance = Mock()
        mock_kite.return_value = mock_kite_instance
        mock_kite_instance.profile.return_value = {'user_name': 'test_user'}
        
        auth_manager = AuthenticationManager(self.config)
        result = auth_manager._adopt_access_token('test_token')
        
        self.assertTrue(result)
        mock_kite_instance.set_access_token.assert_called_once_with('test_token')
    
    @patch('core.authentication.KiteConnect')
    def test_adopt_access_token_failure(self, mock_kite):
        """Test failed access token adoption."""
        mock_kite_instance = Mock()
        mock_kite.return_value = mock_kite_instance
        mock_kite_instance.set_access_token.side_effect = Exception("Invalid token")
        
        auth_manager = AuthenticationManager(self.config)
        result = auth_manager._adopt_access_token('invalid_token')
        
        self.assertFalse(result)
    
    @patch('core.authentication.persist_access_token')
    @patch('core.authentication.KiteConnect')
    def test_authenticate_with_override(self, mock_kite, mock_persist):
        """Test authentication with request token override."""
        mock_kite_instance = Mock()
        mock_kite.return_value = mock_kite_instance
        mock_kite_instance.generate_session.return_value = {
            'access_token': 'generated_token'
        }
        mock_kite_instance.profile.return_value = {'user_name': 'test_user'}
        
        auth_manager = AuthenticationManager(self.config)
        result = auth_manager.authenticate(request_token_override='test_request_token')
        
        self.assertTrue(result)
        mock_kite_instance.generate_session.assert_called_once()
    
    def test_get_kite_client(self):
        """Test getting Kite client."""
        client = self.auth_manager.get_kite_client()
        self.assertIsNotNone(client)


class TestConfigFunctions(unittest.TestCase):
    """Test cases for configuration functions."""
    
    def test_substitute_env_string(self):
        """Test environment variable substitution in strings."""
        os.environ['TEST_VAR'] = 'test_value'
        result = _substitute_env('${TEST_VAR}')
        self.assertEqual(result, 'test_value')
    
    def test_substitute_env_dict(self):
        """Test environment variable substitution in dictionaries."""
        os.environ['TEST_VAR'] = 'test_value'
        result = _substitute_env({'key': '${TEST_VAR}'})
        self.assertEqual(result, {'key': 'test_value'})
    
    def test_substitute_env_list(self):
        """Test environment variable substitution in lists."""
        os.environ['TEST_VAR'] = 'test_value'
        result = _substitute_env(['${TEST_VAR}'])
        self.assertEqual(result, ['test_value'])
    
    def test_substitute_env_no_match(self):
        """Test environment variable substitution with no match."""
        result = _substitute_env('${NONEXISTENT_VAR}')
        self.assertEqual(result, '${NONEXISTENT_VAR}')
    
    @patch('builtins.open', create=True)
    def test_load_config(self, mock_open):
        """Test loading configuration from file."""
        import yaml
        with patch('yaml.safe_load') as mock_yaml_load:
            mock_yaml_load.return_value = {
                'zerodha': {
                    'api_key': '${API_KEY}',
                    'api_secret': '${API_SECRET}'
                }
            }
            os.environ['API_KEY'] = 'real_key'
            os.environ['API_SECRET'] = 'real_secret'
            
            config = load_config()
            
            self.assertEqual(config['zerodha']['api_key'], 'real_key')
            self.assertEqual(config['zerodha']['api_secret'], 'real_secret')


class TestPersistAccessToken(unittest.TestCase):
    """Test cases for persist_access_token function."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env')
        self.temp_file.close()
        self.env_path = self.temp_file.name
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.env_path):
            os.remove(self.env_path)
    
    def test_persist_new_token(self):
        """Test persisting a new access token."""
        persist_access_token('new_token', self.env_path)
        
        with open(self.env_path, 'r') as f:
            content = f.read()
        
        self.assertIn('ZERODHA_ACCESS_TOKEN=new_token', content)
    
    def test_persist_replace_existing_token(self):
        """Test replacing an existing access token."""
        # Write initial token
        with open(self.env_path, 'w') as f:
            f.write('ZERODHA_ACCESS_TOKEN=old_token\n')
        
        persist_access_token('new_token', self.env_path)
        
        with open(self.env_path, 'r') as f:
            content = f.read()
        
        self.assertIn('ZERODHA_ACCESS_TOKEN=new_token', content)
        self.assertNotIn('old_token', content)
    
    def test_persist_preserves_other_env_vars(self):
        """Test that other environment variables are preserved."""
        with open(self.env_path, 'w') as f:
            f.write('OTHER_VAR=value\n')
        
        persist_access_token('new_token', self.env_path)
        
        with open(self.env_path, 'r') as f:
            content = f.read()
        
        self.assertIn('OTHER_VAR=value', content)
        self.assertIn('ZERODHA_ACCESS_TOKEN=new_token', content)


if __name__ == '__main__':
    unittest.main()