curl -d 'entry=Entry1&update=delete' -X 'POST' 'http://10.1.0.4/board/0/' & 
curl -d 'entry=NewEntry1&update=modify' -X 'POST' 'http://10.1.0.2/board/0/'&
curl -d 'entry=NewEntry5&update=modify' -X 'POST' 'http://10.1.0.5/board/1/' 